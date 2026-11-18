# backlog · 口头起飞附上计划路径就超出 40 字，批准不被认（2026-11-18）

## 现象（观察到的偏差，1 次）

change `ship-rerun-hardening` 起飞时，人类发的是「起飞 ship-rerun-hardening 授权提交。飞行计划：<spec.html 绝对路径>」。消息含批准词，但整条超过 `WORD_LIMIT = 40`（`template/.claude/hooks/takeoff-gate.py:45`），`approval_of` 判为非批准，step 0 退出 3。人类改回一句「起飞」后通过，多花了一轮往返。

40 字上限本身是防伪造：长文本里顺带出现的「批准」不能算数。但「批准词开头 + change 名 + 计划路径」是人确认计划时最自然的写法，现在被同一条规则误伤。

## 建议

- 计算长度前先剥掉绝对路径 / `openspec/changes/<name>` 片段与 change 名；或者放行「以批准词开头、其余只含 change 名与路径」的形状。新形状另写测试，保证长文本中途出现的「批准」仍然不算。
- 至少在 exit 3 的提示里点出「消息超过 40 字」，免得人以为是没认出批准词。
