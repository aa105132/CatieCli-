"""
图片本地存储服务
用于保存 Antigravity 生成的图片并返回可访问的 URL
支持自动清理过期图片
"""

import os
import base64
import uuid
import asyncio
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set


class ImageStorage:
    """本地图片存储服务"""
    
    # 图片存储目录（相对于 app 目录）
    # backend/app/services/image_storage.py -> backend/static/images
    STORAGE_DIR = Path(__file__).parent.parent.parent / "static" / "images"
    
    # 待删除的图片文件名集合（用于延迟删除）
    _pending_deletions: Set[str] = set()
    _deletion_lock = threading.Lock()
    
    # 默认图片保留时间（秒）
    DEFAULT_RETENTION_SECONDS = 60  # 1分钟后自动删除
    
    @classmethod
    def init_storage(cls):
        """初始化存储目录"""
        cls.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[ImageStorage] 图片存储目录: {cls.STORAGE_DIR}", flush=True)
        # 启动时清理旧图片
        cls.cleanup_old_images(max_age_hours=1)
    
    @classmethod
    def save_base64_image(cls, base64_data: str, mime_type: str = "image/png", auto_delete_seconds: int = None) -> str:
        """
        保存 base64 图片到本地并返回相对 URL
        
        Args:
            base64_data: base64 编码的图片数据
            mime_type: 图片 MIME 类型
            auto_delete_seconds: 自动删除延迟（秒），None 表示使用默认值
            
        Returns:
            图片的相对 URL 路径 (如 /images/xxx.png)
        """
        # 确保存储目录存在
        cls.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        
        # 根据 MIME 类型确定扩展名
        ext_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }
        ext = ext_map.get(mime_type, ".png")
        
        # 生成唯一文件名
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{timestamp}_{unique_id}{ext}"
        
        # 保存文件
        file_path = cls.STORAGE_DIR / filename
        try:
            image_data = base64.b64decode(base64_data)
            with open(file_path, "wb") as f:
                f.write(image_data)
            print(f"[ImageStorage] ✅ 图片已保存: {filename} ({len(image_data)} bytes)", flush=True)
            
            # 安排自动删除
            delete_delay = auto_delete_seconds if auto_delete_seconds is not None else cls.DEFAULT_RETENTION_SECONDS
            cls.schedule_deletion(filename, delay_seconds=delete_delay)
            
            # 返回相对 URL
            return f"/images/{filename}"
        except Exception as e:
            print(f"[ImageStorage] ❌ 保存图片失败: {e}", flush=True)
            return ""
    
    @classmethod
    def schedule_deletion(cls, filename: str, delay_seconds: int = 60):
        """
        安排延迟删除图片
        
        Args:
            filename: 要删除的文件名
            delay_seconds: 延迟秒数
        """
        def delete_after_delay():
            import time
            time.sleep(delay_seconds)
            file_path = cls.STORAGE_DIR / filename
            try:
                if file_path.exists():
                    file_path.unlink()
                    print(f"[ImageStorage] 🗑️ 图片已自动删除: {filename}", flush=True)
                with cls._deletion_lock:
                    cls._pending_deletions.discard(filename)
            except Exception as e:
                print(f"[ImageStorage] ⚠️ 删除图片失败: {filename}, {e}", flush=True)
        
        with cls._deletion_lock:
            if filename not in cls._pending_deletions:
                cls._pending_deletions.add(filename)
                thread = threading.Thread(target=delete_after_delay, daemon=True)
                thread.start()
                print(f"[ImageStorage] ⏰ 已安排 {delay_seconds}s 后删除: {filename}", flush=True)
    
    @classmethod
    def delete_image(cls, relative_url: str) -> bool:
        """
        立即删除图片
        
        Args:
            relative_url: 图片的相对 URL (如 /images/xxx.png)
            
        Returns:
            是否删除成功
        """
        if not relative_url or not relative_url.startswith("/images/"):
            return False
        
        filename = relative_url.split("/")[-1]
        file_path = cls.STORAGE_DIR / filename
        
        try:
            if file_path.exists():
                file_path.unlink()
                print(f"[ImageStorage] 🗑️ 图片已删除: {filename}", flush=True)
                with cls._deletion_lock:
                    cls._pending_deletions.discard(filename)
                return True
            return False
        except Exception as e:
            print(f"[ImageStorage] ⚠️ 删除图片失败: {filename}, {e}", flush=True)
            return False
    
    @classmethod
    def cleanup_old_images(cls, max_age_hours: int = 1):
        """
        清理过期图片
        
        Args:
            max_age_hours: 图片最大保留时间（小时）
        """
        try:
            if not cls.STORAGE_DIR.exists():
                return
            
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
            deleted_count = 0
            
            for file_path in cls.STORAGE_DIR.iterdir():
                if file_path.is_file() and file_path.suffix in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
                    try:
                        # 从文件名中提取时间戳 (格式: 20260126005455_xxxxxxxx.ext)
                        filename = file_path.stem
                        if "_" in filename:
                            timestamp_str = filename.split("_")[0]
                            if len(timestamp_str) == 14:  # YYYYMMDDHHmmss
                                file_time = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                                if file_time < cutoff_time:
                                    file_path.unlink()
                                    deleted_count += 1
                    except Exception as e:
                        # 无法解析时间戳的文件，检查文件修改时间
                        try:
                            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                            if mtime < cutoff_time:
                                file_path.unlink()
                                deleted_count += 1
                        except:
                            pass
            
            if deleted_count > 0:
                print(f"[ImageStorage] 🧹 已清理 {deleted_count} 个过期图片", flush=True)
        except Exception as e:
            print(f"[ImageStorage] ⚠️ 清理过期图片失败: {e}", flush=True)


# 初始化存储目录
ImageStorage.init_storage()
