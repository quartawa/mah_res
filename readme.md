# 资源高层增量发布约定

MAH-UI 资源更新已支持：

- 优先下载 `hotfix/incremental/patch` 关键词的资源包（高层增量）
- 若无增量包，则回退下载全量包

## Release 资产命名建议

- 全量包：`mah_res-full-v1.0.1.zip`
- 增量包：`mah_res-hotfix-v1.0.1.zip`

只要文件名包含如下关键词即可被识别：

- 增量：`hotfix` / `incremental` / `patch`
- 全量：任意 zip/tar.gz（不含上面增量关键词时视为全量兜底）

## 包内目录结构（必须）

包内应直接放资源根目录，不要额外再套一层总目录（避免解压后出现重复嵌套路径）。

例如当前仓库结构可直接打包为：

```text
image/
index/
```

如果后续新增 `announcement/`、`model/`、`pipeline/`、`assets/` 等目录，也应直接放在包根目录。

## 使用说明

1. 每次资源发版创建 GitHub Release（正式版或预发布均可）
2. 同版本可同时上传 `full` 与 `hotfix` 两个包
3. 客户端点击“资源更新”时会优先选择 `hotfix` 包

## 自动发布（GitHub Actions）

已提供工作流：`.github/workflows/release_resources.yml`

- 自动触发：`push tag v*`
- 手动触发：`workflow_dispatch`

工作流会自动生成并上传：

- `mah_res-full-vX.Y.Z.zip`
- `mah_res-hotfix-vX.Y.Z.zip`

## 你的日常操作

1. 提交资源改动并推送
2. 打标签并推送（例如 `v1.0.1`）
3. 等待 Actions 完成并检查 Release 资产

命令示例：

```bash
git tag v1.0.1
git push origin v1.0.1
```

## 手动触发参数说明

- `tag`: 目标版本号
- `previous_tag`: hotfix 对比基线（可选，不填自动推断）
- `publish_release`: 是否发布到 GitHub Release
