# Frontend Deployment

这个前端镜像使用 Vite 构建静态文件，并用 Nginx 提供访问与 `/api` 反向代理。

## 构建

```bash
docker build -t travel-any-frontend:test .
```

## 运行

把 `BACKEND_ORIGIN` 和 `BACKEND_HOST` 换成你的后端云托管地址。

```bash
docker run --rm -p 8080:80 \
  -e BACKEND_ORIGIN=https://your-backend-domain \
  -e BACKEND_HOST=your-backend-domain \
  travel-any-frontend:test
```

前端访问：

```text
http://localhost:8080
```

健康检查：

```text
http://localhost:8080/
```

后端代理：

```text
http://localhost:8080/api/health
```

## 微信云托管环境变量

- `BACKEND_ORIGIN`: 后端完整地址，例如 `https://xxx.sh.run.tcloudbase.com`
- `BACKEND_HOST`: 后端域名，不带 `https://`，例如 `xxx.sh.run.tcloudbase.com`
- `VITE_AMAP_JS_KEY`: 高德 Web JS API Key，构建前端镜像时注入
- `VITE_AMAP_SECURITY_JS_CODE`: 高德 Web JS API 安全密钥，构建前端镜像时注入

前端生产包默认请求 `/api`，由 Nginx 转发到后端，所以不会再触发浏览器跨域。

`.dockerignore` 已排除 `.env`，不要把本地环境文件上传到云端源码包。需要地图功能时，请在云托管构建配置中填写上面的 `VITE_` 变量。
