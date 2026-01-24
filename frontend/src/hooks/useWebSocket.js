import { useEffect, useRef, useState } from "react";

export function useWebSocket(onMessage) {
  const ws = useRef(null);
  const [connected, setConnected] = useState(false);
  const reconnectTimeout = useRef(null);
  const onMessageRef = useRef(onMessage);
  const isConnecting = useRef(false);
  const authFailCount = useRef(0);  // 认证失败计数

  // 保持 onMessage 引用最新
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    const connect = () => {
      const token = localStorage.getItem("token");
      if (!token) return;

      // 避免重复连接
      if (
        isConnecting.current ||
        (ws.current && ws.current.readyState === WebSocket.OPEN)
      ) {
        return;
      }

      // 关闭旧连接
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }

      isConnecting.current = true;

      // 构建 WebSocket URL
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.hostname;
      // 生产环境不带端口（使用默认的 443/80），开发环境使用 8000
      const port = import.meta.env.DEV ? ":8000" : (window.location.port ? `:${window.location.port}` : "");
      const wsUrl = `${protocol}//${host}${port}/ws?token=${token}`;

      try {
        ws.current = new WebSocket(wsUrl);

        ws.current.onopen = () => {
          console.log("WebSocket 已连接");
          setConnected(true);
          isConnecting.current = false;
          authFailCount.current = 0;  // 连接成功，重置计数
        };

        ws.current.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            // 处理心跳
            if (data.type === "ping") {
              ws.current?.send(JSON.stringify({ type: "pong" }));
              return;
            }

            // 回调处理消息
            onMessageRef.current?.(data);
          } catch (e) {
            console.error("解析 WebSocket 消息失败", e);
          }
        };

        ws.current.onclose = (event) => {
          console.log("WebSocket 已断开, code:", event.code, "reason:", event.reason);
          setConnected(false);
          isConnecting.current = false;
          
          // 检测认证失败 (403 or 4001)
          // 服务器返回 403 时 event.code 通常是 1006 (Abnormal Closure)
          // 但我们自定义了 4001 作为认证失败码
          if (event.code === 4001 || event.code === 4002) {
            authFailCount.current += 1;
            console.warn(`WebSocket 认证失败 (第 ${authFailCount.current} 次)`);
            
            // 连续认证失败超过 2 次，清除 token 让用户重新登录
            if (authFailCount.current >= 2) {
              console.error("WebSocket 认证多次失败，需要重新登录");
              localStorage.removeItem("token");
              // 刷新页面强制重新登录
              window.location.reload();
              return;
            }
          }
          
          // 5秒后重连
          reconnectTimeout.current = setTimeout(connect, 5000);
        };

        ws.current.onerror = (error) => {
          console.error("WebSocket 错误", error);
          isConnecting.current = false;
        };
      } catch (e) {
        console.error("WebSocket 连接失败", e);
        isConnecting.current = false;
      }
    };

    connect();

    return () => {
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }
    };
  }, []); // 空依赖，只在挂载时连接一次

  return { connected };
}
