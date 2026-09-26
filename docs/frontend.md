# 前端预编译策略

硬性要求：**部署侧不需要任何前端工具链**。最终用户机器上不安装 Node、不装 pnpm、不跑构建；
仓库里拿到的就是可以直接被浏览器加载的产物。

## 目录约定（沿用 NeoBot 官方插件的做法）

| 目录 | 内容 | 是否入库 | 打包分发 |
|---|---|---|---|
| `frontend/` | 前端源码（Vite + TypeScript），只有开发者需要 | 入库 | **不**分发 |
| `web/` | 构建产物：`index.html` + `assets/index-<hash>.js` / `.css` | **必须入库** | 分发 |
| `web/image/` | 产物中的图片等静态资源（可选） | 入库 | 分发 |

`node_modules/`、`frontend/dist/`、`.pnpm-store/` 已在 `.gitignore` 中排除。

## 构建基线（与官方插件一致）

`frontend/vite.config.ts`：

```ts
export default defineConfig({
  base: './',            // 支持面板子路径部署（base_path）
  build: {
    outDir: '../web',    // 产物直接落到 web/
    assetsDir: 'assets',
    sourcemap: false,
    emptyOutDir: true,
  },
})
```

构建由开发者执行 `pnpm install && pnpm build`，随后把 `web/` 一起提交。
构建产物与源码必须在同一个 commit 内更新，避免产物与源码脱节。

## 为什么不能提交 node_modules

NeoBot 面板安装插件走 GitHub 归档 zip，有硬性上限：压缩包 ≤ 64MB、解压后 ≤ 256MB、
条目数 ≤ 5000。把依赖目录提交进仓库会直接导致安装失败。

## 服务端形态

插件自身的 HTTP 能力通过 NeoBot 网页面板（官方 `dashboard` 插件）暴露：插件声明
`dependencies = ["dashboard>=1.0.0"]`，实现 `DashboardWebExtension` 协议
（`name` / `prefixes` / `auth_prefixes` / `panel_entry()` / `handle_request()`），
在 `on_load` 里通过能力 `web.register_extension` 注册，静态资源用
`StaticAssetDirectory` 暴露 `web/` 目录。当前版本尚未接入面板。
