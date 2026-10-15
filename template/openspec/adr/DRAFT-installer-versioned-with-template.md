# DRAFT. 安装器与模板同版本：pipe 模式只做引导，交给目标版本自带的 install.sh

- Status: accepted
- Date: 2026-10-09

## Context

`install.sh` 的安装逻辑与 `template/` 同仓演进（#27 起复制 agents / workflows，#35 加 flight 插件安装，#36 加 settings 缺键补齐），一个版本的安装逻辑只对同版本的模板成立。

pipe 模式（`curl … | bash`）下载某个 ref 的归档拿到模板，过去却用「正在运行的这份脚本」的逻辑去安装。ref 与脚本来源不同时，就是新逻辑 × 老模板的混搭。要支持安装历史 tag（stable-v1.0 / stable-v2.0 …），需要一条以后修改安装器时都要遵守的规则。

## Decision

1. **pipe 模式只做引导**：按 ref 下载归档后，交给归档自带的 `install.sh` 执行；安装逻辑永远来自与模板同一个 commit 的脚本。
2. **`install.sh [-u|--upgrade] [TARGET]` 是跨版本契约**：将来的引导器会用这个签名调用任意老版本脚本。新增参数只能是可选的，不得改变这两个参数的语义，也不得依赖交互输入（引导器把 stdin 接到 `/dev/null`）。
3. **本地模式的判据不变**：「脚本旁边有 `template/`」= 本地模式。被交接的脚本靠这一点不再递归下载，以后不得改成别的判据。

## Consequences

- **更易**：任意分支或 tag 都能用 pipe 模式安装，结果与当时 clone 下来本地运行一致；修安装器不会意外改变老版本的安装结果。
- **更难**：老版本安装器的 bug 无法从 main 修复，只能修好后打新 tag；安装器的 CLI 签名被冻结，只能向后兼容地扩展。
- **中性**：pipe 模式多启动一个 bash 进程；flight 插件的 marketplace 仍取仓库默认分支，插件版本不随 tag 钉住（另议）。
