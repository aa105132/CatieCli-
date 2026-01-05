"""
自动数据库迁移工具：从 SQLite 迁移到 PostgreSQL
当检测到 PostgreSQL 配置且存在 SQLite 数据库文件时自动执行
"""
import os
import io
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
import logging

logger = logging.getLogger(__name__)


class DatabaseMigrator:
    def __init__(self, sqlite_path: str, postgres_engine):
        """
        初始化迁移器
        :param sqlite_path: SQLite 数据库文件路径（例如: ./data/gemini_proxy.db）
        :param postgres_engine: PostgreSQL 引擎（复用主应用的连接池）
        """
        self.sqlite_path = sqlite_path
        self.postgres_engine = postgres_engine

        # 构建 SQLite 异步连接 URL
        sqlite_url = f"sqlite+aiosqlite:///{sqlite_path}"

        # SQLite 使用 NullPool
        self.sqlite_engine = create_async_engine(
            sqlite_url,
            echo=False,
            poolclass=NullPool
        )

    async def check_sqlite_has_data(self) -> bool:
        """检查 SQLite 数据库是否包含数据"""
        try:
            async with self.sqlite_engine.begin() as conn:
                # 检查 users 表是否存在且有数据
                result = await conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
                ))
                if not result.scalar():
                    return False

                # 检查是否有用户数据
                result = await conn.execute(text("SELECT COUNT(*) FROM users"))
                count = result.scalar()
                return count > 0
        except Exception as e:
            logger.warning(f"检查 SQLite 数据失败: {e}")
            return False

    async def check_postgres_empty(self) -> bool:
        """检查 PostgreSQL 数据库是否为空"""
        try:
            async with self.postgres_engine.begin() as conn:
                # 检查 users 表是否存在
                result = await conn.execute(text(
                    "SELECT EXISTS (SELECT FROM information_schema.tables "
                    "WHERE table_name = 'users')"
                ))
                table_exists = result.scalar()

                if not table_exists:
                    return True

                # 检查表是否为空
                result = await conn.execute(text("SELECT COUNT(*) FROM users"))
                count = result.scalar()
                return count == 0
        except Exception as e:
            logger.warning(f"检查 PostgreSQL 失败: {e}")
            return True

    def convert_sqlite_to_postgres_types(self, table_name: str, data: dict) -> dict:
        """
        转换 SQLite 数据类型到 PostgreSQL 兼容类型
        :param table_name: 表名
        :param data: 数据字典
        :return: 转换后的数据字典
        """
        # 定义每个表的布尔字段
        boolean_fields = {
            "users": ["is_active", "is_admin"],
            "api_keys": ["is_active"],
            "credentials": ["is_public", "is_active"],
        }

        # 转换布尔字段：SQLite 的 0/1 -> PostgreSQL 的 False/True
        if table_name in boolean_fields:
            for field in boolean_fields[table_name]:
                if field in data and data[field] is not None:
                    # 将 0/1 转换为 False/True
                    data[field] = bool(data[field])

        # 处理 UNIQUE 约束：NULL 值在 PostgreSQL 中也需要唯一性检查
        # SQLite 允许多个 NULL 值，但 PostgreSQL 默认也允许
        # 这里主要是确保空字符串不会被插入到 UNIQUE 字段
        unique_nullable_fields = {
            "users": ["email", "discord_id", "discord_name"],
            "credentials": ["email", "project_id"],
        }

        if table_name in unique_nullable_fields:
            for field in unique_nullable_fields[table_name]:
                if field in data and data[field] == "":
                    # 将空字符串转换为 None
                    data[field] = None

        # 处理整数字段：确保 NULL 值正确传递
        # SQLite 中的 NULL 在某些情况下可能被转换为 0
        integer_nullable_fields = {
            "usage_logs": ["api_key_id", "credential_id", "status_code", "cd_seconds"],
            "credentials": ["user_id"],
        }

        if table_name in integer_nullable_fields:
            for field in integer_nullable_fields[table_name]:
                if field in data and data[field] == 0 and field.endswith("_id"):
                    # 对于外键字段，0 可能应该是 NULL
                    # 但这取决于业务逻辑，这里保持原样
                    pass

        return data

    async def migrate_table(self, table_name: str, batch_size: int = 5000):
        """
        迁移单个表的数据（优化版：使用 COPY 命令和流式读取）
        :param table_name: 表名
        :param batch_size: 批量处理大小
        """
        logger.info(f"开始迁移表: {table_name}")

        try:
            # 获取表结构
            async with self.sqlite_engine.begin() as sqlite_conn:
                result = await sqlite_conn.execute(text(f"SELECT * FROM {table_name} LIMIT 0"))
                columns = list(result.keys())

            # 流式读取数据并使用 COPY 命令插入
            async with self.sqlite_engine.connect() as sqlite_conn:
                # 使用流式游标
                result = await sqlite_conn.stream(text(f"SELECT * FROM {table_name}"))

                total_rows = 0
                buffer = io.StringIO()

                # 获取原始连接
                raw_conn = await self.postgres_engine.raw_connection()
                try:
                    # 获取底层连接对象
                    pg_conn = raw_conn.driver_connection

                    # 使用 COPY 命令（最快的批量插入方式）
                    columns_str = ", ".join(columns)
                    copy_sql = f"COPY {table_name} ({columns_str}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')"

                    async with pg_conn.cursor() as cursor:
                        # 开始 COPY 操作
                        await cursor.copy(copy_sql)

                        # 流式处理数据
                        batch_count = 0
                        async for partition in result.partitions(batch_size):
                            for row in partition:
                                # 转换数据类型
                                row_dict = dict(zip(columns, row))
                                converted = self.convert_sqlite_to_postgres_types(table_name, row_dict)

                                # 构建 CSV 行
                                csv_row = []
                                for col in columns:
                                    value = converted.get(col)
                                    if value is None:
                                        csv_row.append('\\N')
                                    elif isinstance(value, bool):
                                        csv_row.append('t' if value else 'f')
                                    elif isinstance(value, str):
                                        # 转义特殊字符
                                        escaped = value.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace(',', '\\,')
                                        csv_row.append(escaped)
                                    else:
                                        csv_row.append(str(value))

                                buffer.write(','.join(csv_row) + '\n')
                                total_rows += 1

                            # 批量写入
                            if buffer.tell() > 0:
                                buffer.seek(0)
                                await cursor.write(buffer.read().encode('utf-8'))
                                buffer.seek(0)
                                buffer.truncate(0)
                                batch_count += 1
                                logger.info(f"  已处理 {total_rows} 条记录")

                        # 结束 COPY 操作
                        await cursor.write(b'')

                    await pg_conn.commit()
                finally:
                    await raw_conn.close()

                if total_rows == 0:
                    logger.info(f"  ✓ {table_name}: 无数据，跳过")
                    return

                logger.info(f"  ✓ 共迁移 {total_rows} 条记录")

            # 重置自增序列（PostgreSQL 特有）
            if "id" in columns:
                async with self.postgres_engine.begin() as pg_conn:
                    try:
                        # 获取当前最大 ID
                        result = await pg_conn.execute(text(f"SELECT MAX(id) FROM {table_name}"))
                        max_id = result.scalar() or 0

                        # 重置序列
                        await pg_conn.execute(text(
                            f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), :max_id, true)"
                        ), {"max_id": max_id})
                        logger.info(f"  ✓ 序列已重置到 {max_id}")
                    except Exception as e:
                        logger.warning(f"  ! 序列重置失败（可能不影响使用）: {e}")

            logger.info(f"  ✓ {table_name}: 迁移完成")

        except Exception as e:
            logger.error(f"  ✗ {table_name}: 迁移失败 - {e}")
            raise

    async def get_table_order(self) -> dict:
        """
        获取表的正确迁移顺序（按外键依赖）
        返回分组的表名列表，同组的表可以并行迁移
        """
        # 按依赖关系分组
        # 同一组内的表没有相互依赖，可以并行迁移
        return {
            "group_1": ["users", "system_config"],  # 无依赖，可并行
            "group_2": ["api_keys", "credentials"],  # 依赖 users，可并行
            "group_3": ["usage_logs"],  # 依赖前面所有表
        }

    async def migrate_all(self):
        """执行完整迁移流程（优化版：支持并行迁移）"""
        logger.info("=" * 60)
        logger.info("开始数据库迁移：SQLite -> PostgreSQL (优化版)")
        logger.info("=" * 60)

        try:
            # 1. 检查 SQLite 是否有数据
            logger.info("\n[1/5] 检查 SQLite 数据库...")
            has_data = await self.check_sqlite_has_data()
            if not has_data:
                logger.warning("SQLite 数据库为空或无效，取消迁移")
                return False
            logger.info("  ✓ SQLite 数据库包含数据")

            # 2. 检查 PostgreSQL 是否为空
            logger.info("\n[2/5] 检查 PostgreSQL 数据库...")
            is_empty = await self.check_postgres_empty()
            if not is_empty:
                logger.warning("PostgreSQL 数据库已包含数据，跳过迁移")
                return False
            logger.info("  ✓ PostgreSQL 数据库为空，可以迁移")

            # 3. 创建表结构（通过 init_db）
            logger.info("\n[3/5] 创建 PostgreSQL 表结构...")
            from app.database import init_db
            await init_db(skip_migration_check=True)  # 跳过迁移检查避免递归
            logger.info("  ✓ 表结构创建完成")

            # 4. 串行迁移数据（避免连接数超限）
            logger.info("\n[4/5] 迁移数据...")
            table_groups = await self.get_table_order()

            for group_name, tables in table_groups.items():
                logger.info(f"\n  处理 {group_name}: {', '.join(tables)}")
                # 串行迁移避免连接数超限
                for table in tables:
                    await self.migrate_table(table)

            # 5. 验证数据完整性
            logger.info("\n[5/5] 验证迁移结果...")
            await self.verify_migration()

            logger.info("\n" + "=" * 60)
            logger.info("✓ 数据迁移完成！")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(f"\n✗ 迁移失败: {e}", exc_info=True)
            return False
        finally:
            await self.sqlite_engine.dispose()
            # PostgreSQL 引擎由主应用管理，不在这里释放

    async def verify_migration(self):
        """验证迁移的数据完整性"""
        table_groups = await self.get_table_order()

        # 展平所有表名
        all_tables = []
        for tables in table_groups.values():
            all_tables.extend(tables)

        for table_name in all_tables:
            try:
                # 统计 SQLite 记录数
                async with self.sqlite_engine.begin() as sqlite_conn:
                    result = await sqlite_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    sqlite_count = result.scalar()

                # 统计 PostgreSQL 记录数
                async with self.postgres_engine.begin() as pg_conn:
                    result = await pg_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    pg_count = result.scalar()

                if sqlite_count == pg_count:
                    logger.info(f"  ✓ {table_name}: {pg_count} 条记录")
                else:
                    logger.error(f"  ✗ {table_name}: 数量不匹配 (SQLite: {sqlite_count}, PostgreSQL: {pg_count})")
                    raise Exception(f"表 {table_name} 数据验证失败")

            except Exception as e:
                logger.error(f"  ✗ {table_name}: 验证失败 - {e}")
                raise


async def auto_migrate_if_needed(sqlite_path: str, postgres_engine) -> bool:
    """
    执行数据库迁移（由 init_db 调用，已完成文件检查）
    :param sqlite_path: SQLite 数据库文件路径
    :param postgres_engine: PostgreSQL 引擎（复用主应用的连接池）
    :return: True 表示执行了迁移，False 表示未执行
    """
    logger.info(f"检测到 SQLite 数据库: {sqlite_path}")

    # 创建迁移器并执行迁移（复用主应用的 PostgreSQL 引擎）
    migrator = DatabaseMigrator(sqlite_path, postgres_engine)
    success = await migrator.migrate_all()

    if success:
        # 迁移成功，备份原文件
        backup_path = f"{sqlite_path}.bak"
        logger.info(f"\n备份原数据库文件: {sqlite_path} -> {backup_path}")
        os.rename(sqlite_path, backup_path)
        logger.info("✓ 备份完成")
        return True

    return False
