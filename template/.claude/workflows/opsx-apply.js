// opsx-apply · 飞行模式的确定性调度脚本（Claude Code 命名工作流）
// 由 /opsx-apply 命令以 args 启动：
//   { change, changeDir, hooksDir, agentsDir, waves, useAgentTypes, branch, turns, models, efforts }
//   change        change 名，如 "add-user-export"
//   changeDir     相对仓库根，如 "openspec/changes/add-user-export"
//   hooksDir      相对仓库根，如 ".claude/hooks"
//   agentsDir     相对仓库根，如 ".claude/agents"（agent 定义未注册时让默认 subagent 先读定义）
//   waves         slice-gate.py waves 的输出，如 [["S1","S2"],["S3"],["S4","S5"]]
//   useAgentTypes false 时不传 agentType（agent 定义未注册的仓库回退为默认 workflow subagent）
//   branch        可选，change 分支名（起飞时 git branch --show-current）；每个执行体的 start 带 --expect-branch，据此做基点祖先校验
//   turns         可选，{ S1: "standard", S2: "large", ... }（slice-gate.py turns 的输出）；large 派 slice-executor-large（80 轮），缺省全部 standard（40 轮）
//   deps          可选，{ S3: ["S1","S2"], ... }（来自 slices.json）；依赖已 blocked 的切片直接记 blocked，不白跑
//                 blocked 条目形如 { slice, kind: 'gate' | 'infra', reason }：gate = 切片门禁红；infra = agent 重派后仍未返回 / 依赖跳过 / integrator 合回失败。
//                 blocked 只进 PR 正文作说明；draft / ready 由 slice-gate.py ship 按 gate-report.md 裁决，不看本列表。
//   models        必填：{ executor, reviewer, integrator }，按角色显式路由（铁律：不得留空让 env 默认兜底）
//                 executor / reviewer = 会话主模型别名（如 "opus" / "fable"）；integrator = 低档模型（"sonnet"）
//                 可选 executor-large（大片档执行体）/ fixer（批量修复与 wave 跨片修复），缺省取 executor 的值
//   efforts       可选：{ executor: "high", reviewer: "high", integrator: "low" }；executor-large / fixer 缺省取 efforts.executor
//                 每个角色的 effort 只能取 low / medium / high / xhigh / max，否则起飞前抛错
//   landed        可选，{ S1: "<commit>", ... }（slice-gate.py landed 的输出）；上次飞行已合回的切片不再派执行体，评审照派，返回值标 landed
// 结构：wave 内 parallel 派发切片（一律 isolation: worktree）→ 门禁红或执行体未返回 / 抛错重试一次 → 每个 wave 由 integrator 合回，
//       合回后做集成检查（wave-check），红了当场派一个跨片修复执行体，绿了合回，仍红按红的种类定停飞范围 →
//       评审只 push 不 await（离关键路径）→ Fix 阶段汇总 CRITICAL/HIGH 一次批量修复 → Finalize 全量门禁。
// 不用时间戳与随机数（运行时为可续跑而禁止它们），脚本本身不碰文件系统，全部由 agent 执行。
export const meta = {
  name: 'opsx-apply',
  description: '按 slices.json 逐 wave 并行实现切片；每切片机械门禁；评审离关键路径；一次批量修复；全量门禁',
  whenToUse: '由 /opsx-apply 命令在 slices.json lint 通过后启动；不要手工调用',
  phases: [
    { title: 'Implement', detail: '按 wave 并行派发 slice-executor，门禁红重试一次' },
    { title: 'Review', detail: '每切片一个 code-reviewer，并行、不阻塞下一个 wave' },
    { title: 'Fix', detail: '汇总 CRITICAL/HIGH，一个执行体一次修完' },
    { title: 'Finalize', detail: 'integrator 跑全量门禁与 scenario 状态' },
  ],
}

const { change, changeDir, hooksDir, waves, useAgentTypes } = args
const agentsDir = args.agentsDir || '.claude/agents'
const branch = args.branch || null
const deps = args.deps || {}   // 可选：{ S3: ["S1","S2"], ... }；依赖已 blocked 的切片不再派发，直接记 blocked
const landed = args.landed || {}   // 可选：{ S1: "<commit>", ... }；上次飞行已合回的切片
const changeName = changeDir.split('/').filter(Boolean).pop()

// ---- 轮次档：按 args.turns 给每片选执行体定义；CAPS 必须等于两份定义文件 frontmatter 的 maxTurns
const turns = args.turns || {}
const CAPS = { standard: 40, large: 80 }
const TIER_NAME = { standard: '标准档', large: '大片档' }
const tierOf = (s) => (turns[s] === 'large' ? 'large' : 'standard')
const execDef = (s) => (tierOf(s) === 'large' ? 'slice-executor-large' : 'slice-executor')

// ---- 模型路由（铁律：按角色显式声明，缺一即拒绝起飞）
// 5 个角色：executor-large（大片档执行体）与 fixer（批量修复 / wave 跨片修复）缺省取 executor 的值
const EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max']
const ROLES = ['executor', 'executor-large', 'fixer', 'reviewer', 'integrator']
const models = Object.assign({}, args.models || {})
for (const role of ['executor', 'reviewer', 'integrator']) {
  if (!models[role]) throw new Error(`args.models.${role} 缺失：模型必须按角色显式路由（executor/reviewer = 会话主模型，integrator = sonnet），不能留空让 CLAUDE_CODE_SUBAGENT_MODEL 默认兜底`)
}
const efforts = Object.assign({ executor: 'high', reviewer: 'high', integrator: 'low' }, args.efforts || {})
for (const role of ['executor-large', 'fixer']) {
  if (!models[role]) models[role] = models.executor
  if (!efforts[role]) efforts[role] = efforts.executor
}
for (const role of ROLES) {
  if (!EFFORTS.includes(efforts[role])) throw new Error(`args.efforts.${role} = ${efforts[role]} 不合法：effort 只能取 ${EFFORTS.join(' / ')}`)
}
const execRole = (s) => (tierOf(s) === 'large' ? 'executor-large' : 'executor')
log(`模型路由：` + ROLES.map((r) => `${r}=${models[r]}/${efforts[r]}`).join(' · '))

const typed = (name) => (useAgentTypes === false ? {} : { agentType: name })
// agent 定义未注册（useAgentTypes=false）时，纪律仍以定义文件为准：让默认 subagent 先读它再干活
const rules = (name) => (useAgentTypes === false ? `先 Read ${agentsDir}/${name}.md，严格按它的纪律执行（它就是你的角色定义）。\n` : '')
const gateCmd = (s) => `python3 ${hooksDir}/slice-gate.py gate ${s} --change-dir ${changeDir}`
// cont：重派时传上一轮 gate JSON 的 commit，start --continue 由脚本把上一轮的全部提交接到当前 HEAD；区间起点由脚本按 change 分支算
// resume：上一轮执行体未返回时，start 带 --resume-checkpoint 把 hook 快照的半成品恢复为未提交改动
// branch：start 校验 HEAD 是 change 分支的后代（基点校验），不是则非 0 退出并打印 G0 JSON
const startCmd = (s, cont, resume) => `python3 ${hooksDir}/slice-gate.py start ${s} --change-dir ${changeDir}`
  + (cont ? ` --continue ${cont}` : '') + (resume ? ' --resume-checkpoint' : '') + (branch ? ` --expect-branch ${branch}` : '')
// 执行体未返回（多为撞 maxTurns）时的重派标记：没有门禁结论，也没有 commit / base 可接
const NO_RETURN = { noReturn: true }

const GATE = {
  type: 'object',
  required: ['slice', 'ok', 'commit', 'failed'],
  properties: {
    slice: { type: 'string' },
    ok: { type: 'boolean' },
    commit: { type: 'string' },
    failed: { type: 'array', items: { type: 'string' } },
    warnings: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    // 本轮 start 记录的区间起点 sha；只作留档，重派不再回传（start --continue 由脚本按 change 分支算区间起点）
    base: { type: 'string' },
    // 合规天花板行 [[相对路径, 行号（整数）, 限制, 升级路径], ...]：门禁在临时 worktree 里算出，靠这个字段带回给 record 写进飞行记录
    // 内层元素无类型约束，执行体可能转写出非整数行号 → 消费侧 slice-gate.py 的 ceiling_rows_from_json 负责宽容化，不在这里 fail
    ceilings: { type: 'array', items: { type: 'array' } },
  },
}
const FINDINGS = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'file', 'line', 'summary', 'fix'],
        properties: {
          severity: { enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
          file: { type: 'string' },
          line: { type: 'integer' },
          summary: { type: 'string' },
          fix: { type: 'string' },
        },
      },
    },
  },
}
// wave 合回的返回结构：合回不是切片，没有 slice / commit；只看 ok 与 failed
const MERGE = {
  type: 'object',
  required: ['ok', 'failed'],
  properties: {
    ok: { type: 'boolean' },
    merged: { type: 'array', items: { type: 'string' } },
    failed: { type: 'array', items: { type: 'string' } },
    warnings: { type: 'array', items: { type: 'string' } },
    // wave 集成检查（slice-gate.py wave-check）的 JSON；子命令不存在（hooks 未升级）或本次未点名时为 null / 缺省
    check: { type: ['object', 'null'] },
  },
}

const executorPrompt = (s, retryOf) => [
  rules(execDef(s)) + `你在仓库根（cwd）。为 OpenSpec change \`${change}\` 实现切片 ${s}。`,
  `切片包：${changeDir}/slices/${s}.md（scenario、owns、verify、接口摘要都在里面，先读它）。`,
  // 重派：start --continue 由脚本接上一轮的全部提交（临时 worktree 可能是新开的）；hooks 未升级时回退为手工 cherry-pick；首轮基点由 start --expect-branch 校验
  retryOf && retryOf.noReturn
    ? `第一步运行 \`${startCmd(s, null, true)}\`（\`--resume-checkpoint\` 从快照恢复上一轮半成品）。`
    : retryOf && retryOf.commit
      ? `第一步运行 \`${startCmd(s, retryOf.commit)}\`（\`--continue\` 由脚本把上一轮的全部提交接到当前 HEAD，输出里的 continued 写明接了几个）。\n` +
        `start 报 unrecognized arguments: --continue（hooks 未升级）→ 运行 \`git rev-parse HEAD\`，不等于 ${retryOf.commit} 就 \`git cherry-pick ${retryOf.commit}\`（冲突则 \`git cherry-pick --abort\` 并返回 failed 为 ["G0 base: cherry-pick ${retryOf.commit} 冲突"] 的 JSON），再运行不带 --continue 的 start。`
      : `第一步运行 \`${startCmd(s)}\`。`,
  'start 非 0 退出（G0 基点校验未通过）→ 不做任何改动，把它打印的 JSON 原样作为最终输出。',
  // 上一轮无产出（start 以 G0 拒绝，commit 为空）→ 走首轮分支从头实现，而不是「只修门禁项」
  retryOf && retryOf.noReturn
    ? '上一轮执行体未返回（多为撞 maxTurns 轮次上限），没有门禁结论；start 会把上一轮半成品恢复为未提交改动（看 start 输出的 checkpoint.restored），先 git status / git diff 看清已完成部分，在其上继续、不要重做；收尾仍按切片包 TDD、每切片一个 commit。'
    : retryOf && retryOf.commit
      ? `上一轮门禁未过：${JSON.stringify(retryOf.failed)}。只修这些门禁项，不扩大范围。`
      : '按切片包 TDD 实现，只写 owns 内文件，每切片一个 commit。',
  `收尾运行 \`${gateCmd(s)}\`，把它打印的 JSON 原样作为最终输出。`,
].join('\n')

// fixOf：wave 集成检查红之后的跨片修复（{ wave, failed }）——「切片包」那一行换成修复的来由
const reviewPrompt = (s, gate, fixOf) => [
  rules('code-reviewer') + `评审模式：full。审 OpenSpec change \`${change}\` ${fixOf ? '' : '切片 '}${s} 的实现 commit：\`git show --submodule=diff ${gate.commit}\`。`,
  fixOf
    ? `这是 wave ${fixOf.wave} 集成检查红之后的跨片修复，失败项：${JSON.stringify(fixOf.failed)}。`
    : `切片包（scenario 与约束）：${changeDir}/slices/${s}.md。`,
  `门禁 JSON（已机械判定 verify / 配对 / GWT / 所有权 / scenario 状态，不要重报）：${JSON.stringify(gate)}。`,
  `evidence：${changeDir}/evidence.log（本切片的测试运行留痕，可 grep）。`,
  '不重跑测试套件、不轮询；至多 1 次定向抽查。',
  '输出结构化 findings（severity / file / line / summary / fix）。',
].join('\n')

// 临时 worktree 里的修复执行体（Fix 阶段与 wave 跨片修复共用）开工前的两道校验：基点祖先校验 + submodule 填充；tag 是失败时返回 JSON 的 slice 字段
const baseCheckLines = (tag) => [
  // 与切片执行体同一道防线：临时 worktree 可能不是从 change 分支最新 commit 分叉；start 可能因无 fix 条目被拒，所以先单独校验
  branch
    ? `第一步做基点校验：运行 \`git merge-base --is-ancestor $(git rev-parse ${branch}) HEAD\`；非 0 退出（HEAD 不是分支 ${branch} 最新 commit 的后代）→ 不做任何改动，直接返回 {"slice":"${tag}","ok":false,"commit":"<实际 HEAD>","failed":["G0 base: HEAD 不是分支 ${branch} 的后代"]}。`
    : '',
  `${branch ? '再' : '先'}运行 \`python3 ${hooksDir}/slice-gate.py sub-sync --change-dir ${changeDir}` + (branch ? ` --expect-branch ${branch}` : '') + '`' +
    `（按 gitlink 填充隔离 worktree 的 submodule；无 submodule 时是空操作）；非 0 退出 → 不做任何改动，直接返回 {"slice":"${tag}","ok":false,"commit":"<实际 HEAD>","failed":<它 JSON 的 failed>}。`,
]
// G0 基点拒绝的 commit 是旧基点上的 HEAD，不能合回：与未返回同样重派一次（新开的临时 worktree 可能基点正确）
const baseRejected = (r) => !!r && (r.failed || []).some((f) => f.startsWith('G0'))
const shq = (s) => `'${String(s).replace(/'/g, `'\\''`)}'`

const reviews = []
const results = []
const blocked = []
const wavesOut = []
// 集成检查仍红（非守护）的 wave 里已合回的切片 → 所在 wave 号；只用于依赖判断，不进 blocked
const waveBlocked = new Map()
// 守护（G15）在跨片修复后仍红的 wave 号：后续 wave 一律不再派发
let stopAll = 0

// 评审员抛错不重派、不拖垮工作流：记 blocked（infra），切片级评审缺失由 /pr-ship 的整 PR 评审兜住
const pushReview = (s, prompt) => reviews.push(agent(prompt, { label: `review:${s}`, phase: 'Review', schema: FINDINGS, model: models.reviewer, effort: efforts.reviewer, ...typed('code-reviewer') })
    .catch(() => { blocked.push({ slice: `review:${s}`, kind: 'infra', reason: '切片 ' + s + ' 评审未返回（不重派，PR 评审兜底）' }); return null }))

for (const [i, allWave] of waves.entries()) {
  phase('Implement')
  if (stopAll) {
    for (const s of allWave) blocked.push({ slice: s, kind: 'infra', reason: `wave ${stopAll} 集成检查红（守护），后续切片不再派发` })
    log(`wave ${i + 1}/${waves.length}: 跳过（wave ${stopAll} 集成检查红（守护））`)
    continue
  }
  const blockedIds = new Set([...blocked.map((b) => b.slice), ...waveBlocked.keys()])
  const skipped = allWave.filter((s) => (deps[s] || []).some((d) => blockedIds.has(d)))
  for (const s of skipped) {
    const hit = (deps[s] || []).filter((d) => blockedIds.has(d))
    const direct = hit.filter((d) => !waveBlocked.has(d))
    const viaWave = hit.filter((d) => waveBlocked.has(d))
    const reason = [direct.length ? `依赖已 blocked：${direct.join(', ')}` : '']
      .concat(viaWave.map((d) => `依赖的切片所在的 wave ${waveBlocked.get(d)} 集成检查红：${d}`)).filter(Boolean).join('；')
    blocked.push({ slice: s, kind: 'infra', reason })
  }
  // 上次飞行已合回的切片：不派执行体，结论直接记 ok
  const landedHere = allWave.filter((s) => landed[s] && !skipped.includes(s))
  for (const s of landedHere) results.push({ slice: s, ok: true, commit: landed[s], failed: [], landed: true })
  const wave = allWave.filter((s) => !skipped.includes(s) && !landedHere.includes(s))
  log(`wave ${i + 1}/${waves.length}: ${wave.join(', ') || (landedHere.length ? '(无待派切片)' : '(全部因依赖 blocked 跳过)')}` +
    (landedHere.length ? `；已落地跳过：${landedHere.join(', ')}` : ''))
  if (!wave.length && !landedHere.length) continue
  // 每个执行体（含单片 wave）都在临时 worktree 里跑，由 integrator 合回：主 worktree 不留执行体的 .openspec-slice 标记
  const iso = 'worktree'
  // 执行体没交回结构化结果时 agent 调用会抛错（运行时实测），与返回空值同样按未返回处理
  const run = (s, retryOf) => agent(executorPrompt(s, retryOf),
    { label: retryOf ? `${s}:retry` : s, isolation: iso, schema: GATE, model: models[execRole(s)], effort: efforts[execRole(s)], ...typed(execDef(s)) })
    .catch(() => null)
  const done = await parallel(wave.map((s) => () =>
    run(s).then((r) => (!r || !r.ok) ? run(s, r || NO_RETURN) : r)))
  for (const [k, r] of done.entries()) {
    const s = wave[k]
    if (!r) {
      const t = tierOf(s)
      blocked.push({ slice: s, kind: 'infra', reason: `执行体未返回（已重派一次）：${TIER_NAME[t]}上限 ${CAPS[t]} 轮；半成品快照在 refs/flight/${changeName}/${s}，重新起飞的首轮会清掉它，要保留先在新 worktree 里 start ${s} --resume-checkpoint` })
      continue
    }
    results.push(r)
    if (!r.ok) { blocked.push({ slice: s, kind: 'gate', reason: r.failed.join('; ') }); continue }
  }
  const merged = wave.filter((s, k) => done[k] && done[k].ok)
  // wave 集成检查：守护 + 受影响的测试；extra 给跨片修复收尾的 --fix-base
  const waveCmd = (extra) => `python3 ${hooksDir}/slice-gate.py wave-check --change-dir ${changeDir} --wave ${i + 1} --of ${waves.length}` + (extra || '')
  const checkStep = `把它打印的 JSON 原样放进返回 JSON 的 check 字段（退出 1 = 红，是正常结论，照样带回，不要自己修、不要重跑）；它报 invalid choice（hooks 未升级，子命令不存在）→ check 写 null，warnings 记一句`
  if (merged.length || landedHere.length) {
    const pairs = merged.map((s) => `${s}=${done[wave.indexOf(s)].commit}`)
    // 临时 worktree 里跑出的门禁结论（含天花板行）不会随 commit 进分支，由 integrator 用 record --json 幂等写回
    const recordCmds = merged.map((s) => {
      const g = done[wave.indexOf(s)]
      const payload = { slice: s, ok: !!g.ok, commit: g.commit, failed: g.failed || [], warnings: g.warnings || [], ceilings: g.ceilings || [] }
      return `python3 ${hooksDir}/slice-gate.py record --change-dir ${changeDir} --json ${shq(JSON.stringify(payload))}`
    })
    const integPrompt = merged.length
      ? rules('integrator') + `按 agent 定义第 0 项先把 ${changeDir} 内未提交的飞行记录文件（timeline.md / gate-report.md / evidence.log）提交掉；` +
        `再按第 1 项运行 \`python3 ${hooksDir}/slice-gate.py merge ${pairs.join(' ')}\` 合回切片 ${merged.join(', ')}（它逐片 git merge --no-ff 并处理 submodule gitlink；报 invalid choice（子命令不存在）→ 按第 1 项的回退逐片 git merge --no-ff；退出 1 → 把它 JSON 的 failed 原样作为返回的 failed、ok:false，不再往下）。` +
        `合回后逐条运行（把临时 worktree 里的门禁结论写回分支）：\n${recordCmds.join('\n')}\n` +
        `然后按第 2 项刷新 ${changeDir}/slices/_interfaces.md，并 \`python3 ${hooksDir}/timeline.py record integrate --change-dir ${changeDir} --note "wave ${i + 1}"\`，最后再按第 0 项把飞行记录提交。` +
        `之后按第 5 项运行 \`${waveCmd()}\`（wave 集成检查；merge 退出 1 时不运行它），${checkStep}；再按第 0 项提交一次飞行记录。` +
        '本次只合回，不要运行第 3 项（全量门禁 final）——后续 wave 的 scenario 还没解锁，现在跑必然红。返回 JSON {ok, merged, failed, warnings, check}。'
      : rules('integrator') + `本 wave 的切片 ${landedHere.join(', ')} 上次飞行已合回分支，不要运行第 1 项的 merge 与 record。` +
        `按 agent 定义第 0 项先把 ${changeDir} 内未提交的飞行记录文件提交掉；再按第 5 项运行 \`${waveCmd()}\`（wave 集成检查），${checkStep}；再按第 0 项提交一次飞行记录。` +
        '不要运行第 3 项（全量门禁 final）。返回 JSON {ok: true, merged: [], failed: [], warnings: [], check}。'
    // integrator 抛错与未返回同样重派一次；返回 ok:false（合回冲突）是确定性的，不重派
    const callInteg = (retry) => agent(integPrompt,
      { label: `integrate:w${i + 1}` + (retry ? ':retry' : ''), schema: MERGE, model: models.integrator, effort: efforts.integrator, ...typed('integrator') })
      .catch(() => null)
    let integ = await callInteg(false)
    if (!integ) integ = await callInteg(true)
    if (!integ || !integ.ok) blocked.push({ slice: `wave${i + 1}`, kind: 'infra', reason: integ ? integ.failed.join('; ') : 'integrator 未返回（已重派一次）' })
    else if (!integ.check) wavesOut.push({ wave: i + 1, skipped: 'integrator 未带回集成检查结果' })
    else if (integ.check.ok) wavesOut.push({ wave: i + 1, ok: true, failed: [], tests: integ.check.tests || null, fix: null })
    else {
      // 集成检查红：当场派一个跨片修复执行体（隔离 worktree，不受切片 owns 限制），红的检查就是先失败的测试
      const chk = integ.check
      const runWaveFix = (retry) => agent([
        rules('slice-executor') + `你在仓库根。这是 OpenSpec change \`${change}\` 的**跨片修复**，不是切片：wave ${i + 1} 合回后的集成检查红了。` +
          '不运行 `slice-gate.py start` 与 `slice-gate.py gate`；不受任何切片的 owns 限制，但只改让下列失败项变绿所必需的文件。',
        retry ? '上一轮修复执行体未返回或被 G0 基点校验拒绝，从头修。' : '',
        ...baseCheckLines('wave'),
        '记下此刻的 `git rev-parse HEAD`，后面叫 <base>。',
        `失败项：${JSON.stringify(chk.failed)}。红的集成检查就是先失败的测试；缺陷需要新测试才能钉住时照 TDD 补。`,
        `逐条 commit（fix: 前缀），不 push，不提交 ${changeDir} 下的飞行记录文件。`,
        `收尾运行 \`${waveCmd(' --fix-base <base>')}\`，把它打印的 JSON 原样作为最终输出。`,
      ].filter(Boolean).join('\n'), { label: `fix:w${i + 1}` + (retry ? ':retry' : ''), phase: 'Fix', isolation: 'worktree', schema: GATE, model: models.fixer, effort: efforts.fixer, ...typed('slice-executor') })
        .catch(() => null)
      let wf = await runWaveFix(false)
      if (!wf || baseRejected(wf)) wf = (await runWaveFix(true)) || wf
      const fixInfo = (ok) => (wf ? { commit: wf.commit, ok, files: (wf.fix || {}).files || [], outside_owns: (wf.fix || {}).outside_owns || [] } : null)
      let red = false
      if (wf && wf.ok && wf.commit && !baseRejected(wf)) {
        const callWaveMerge = (retry) => agent(
          rules('integrator') + `按 agent 定义第 0 项先把 ${changeDir} 内未提交的飞行记录文件提交掉；` +
          `再按第 1 项运行 \`python3 ${hooksDir}/slice-gate.py merge wavefix${i + 1}=${wf.commit}\` 合回 wave ${i + 1} 的跨片修复（报 invalid choice（子命令不存在）→ 按第 1 项的回退 git merge --no-ff；退出 1 → 把它 JSON 的 failed 原样作为返回的 failed、ok:false，不再往下）。` +
          `合回后运行（把临时 worktree 里的集成检查结论写回分支）：\`python3 ${hooksDir}/slice-gate.py record --change-dir ${changeDir} --json ${shq(JSON.stringify(wf))}\`；` +
          `再 \`python3 ${hooksDir}/timeline.py record wave-fix --change-dir ${changeDir} --note "wave ${i + 1}"\`，最后按第 0 项再提交一次飞行记录。` +
          '不要运行第 3 项（全量门禁 final）。返回 JSON {ok, merged, failed, warnings}。',
          { label: `integrate:w${i + 1}:fix` + (retry ? ':retry' : ''), schema: MERGE, model: models.integrator, effort: efforts.integrator, ...typed('integrator') })
          .catch(() => null)
        let back = await callWaveMerge(false)
        if (!back) back = await callWaveMerge(true)
        if (back && back.ok) {
          pushReview(`wavefix${i + 1}`, reviewPrompt(`wavefix${i + 1}`, wf, { wave: i + 1, failed: chk.failed }))
          wavesOut.push({ wave: i + 1, ok: true, failed: chk.failed, fix: fixInfo(true) })
        } else {
          red = true
          if (back) blocked.push({ slice: `wave${i + 1}`, kind: 'gate', reason: `wave ${i + 1} 集成检查红，跨片修复合回失败：${back.failed.join('; ')}（修复提交 ${wf.commit}）` })
          else blocked.push({ slice: `wave${i + 1}`, kind: 'infra', reason: `wave ${i + 1} 集成检查红，跨片修复的合回 integrator 未返回（已重派一次）（修复提交 ${wf.commit}）` })
        }
      } else if (!wf) {
        red = true
        blocked.push({ slice: `wave${i + 1}`, kind: 'infra', reason: `wave ${i + 1} 集成检查红，跨片修复执行体未返回（已重派一次）：${chk.failed.join('; ')}` })
      } else if (baseRejected(wf)) {
        red = true
        blocked.push({ slice: `wave${i + 1}`, kind: 'infra', reason: wf.failed.join('; ') })
      } else {
        red = true
        blocked.push({ slice: `wave${i + 1}`, kind: 'gate', reason: `wave ${i + 1} 集成检查红，跨片修复后仍红：${(wf.failed || []).join('; ')}（修复提交 ${wf.commit}，未合回）` })
      }
      if (red) {
        const last = (wf && !baseRejected(wf) && wf.failed && wf.failed.length) ? wf.failed : chk.failed
        // 守护仍红 → 后续 wave 全部停；只有测试红 → 只停依赖本 wave 已合回切片的后续切片
        if (last.some((f) => f.startsWith('G15'))) stopAll = i + 1
        else for (const s of [...merged, ...landedHere]) waveBlocked.set(s, i + 1)
        wavesOut.push({ wave: i + 1, ok: false, failed: last, fix: fixInfo(false) })
      }
    }
  }
  for (const s of merged) pushReview(s, reviewPrompt(s, done[wave.indexOf(s)]))
  for (const s of landedHere) pushReview(s, reviewPrompt(s, { slice: s, ok: true, commit: landed[s], failed: [] }))
}

phase('Fix')
const findings = (await Promise.all(reviews)).filter(Boolean).flatMap((r) => r.findings || [])
const blocking = findings.filter((f) => f.severity === 'CRITICAL' || f.severity === 'HIGH')
const deferred = findings.filter((f) => f.severity !== 'CRITICAL' && f.severity !== 'HIGH')
log(`评审 finding：阻断 ${blocking.length}，非阻断 ${deferred.length}`)
let fix = null
if (blocking.length) {
  // fix 也是执行体：agent 调用抛错与未返回同样处理，重派一次；仍为空记 blocked（infra），Finalize 照常跑（mergeFix 自动跳过）
  const runFix = (retry) => agent([
    rules('slice-executor') + `你在仓库根。一次性修复 OpenSpec change \`${change}\` 评审挡下的 ${blocking.length} 条 CRITICAL/HIGH，逐条 commit（fix: 前缀），不 push。`,
    retry ? '上一轮 fix 执行体未返回（多为撞 maxTurns）或被 G0 基点校验拒绝，没有可合回的修复：从头按 finding 清单修复。' : '',
    ...baseCheckLines('fix'),
    `然后运行 \`${startCmd('fix')}\` 记录起点（fix 不受单切片所有权限制：slices.json 若无 fix 条目，start 会拒绝，此时跳过 start${branch ? '；基点已由第一步校验' : ''}）。`,
    `finding 清单：${JSON.stringify(blocking)}`,
    // fix 在临时 worktree 里跑，timeline 记录进不了分支：record fix 由 finalize 合回后写
    `每条修复都要有先失败的测试；修完运行 \`python3 ${hooksDir}/slice-gate.py final --change-dir ${changeDir}\`，把 JSON 原样返回。`,
  ].filter(Boolean).join('\n'), { label: retry ? 'fix:retry' : 'fix', isolation: 'worktree', schema: GATE, model: models.fixer, effort: efforts.fixer, ...typed('slice-executor') })
    .catch(() => null)
  fix = await runFix(false)
  if (!fix || baseRejected(fix)) fix = (await runFix(true)) || fix
  if (!fix) blocked.push({ slice: 'fix', kind: 'infra', reason: 'fix agent 未返回（已重派一次）' })
  else if (baseRejected(fix)) { blocked.push({ slice: 'fix', kind: 'infra', reason: fix.failed.join('; ') }); fix = null }
}

phase('Finalize')
// fix 在临时 worktree 里提交：合回指令必须先于 final，否则 final 验的是没有修复的分支
const mergeFix = fix && fix.commit
  ? `再按第 1 项运行 \`python3 ${hooksDir}/slice-gate.py merge fix=${fix.commit}\` 合回 fix 的 commit（报 invalid choice（子命令不存在）→ 按第 1 项的回退 git merge --no-ff；冲突 → 返回 ok:false 且 failed 写「merge fix 冲突」，不再往下跑）；` +
    `\`python3 ${hooksDir}/timeline.py record fix --change-dir ${changeDir} --note "blocking=${blocking.length}"\`；`
  : ''
// final-gate 同 integrator：抛错与未返回重派一次，仍为空记 blocked（infra），返回的 final 为 null
const callFinal = (retry) => agent(
  rules('integrator') + `按 agent 定义第 0 项先提交 ${changeDir} 内未提交的飞行记录文件；` + mergeFix +
  `\`python3 ${hooksDir}/timeline.py record review --change-dir ${changeDir} --note "findings=${findings.length} blocking=${blocking.length} deferred=${deferred.length}"\`；` +
  `再按第 3 项运行 \`python3 ${hooksDir}/slice-gate.py final --change-dir ${changeDir}\`，` +
  `再 \`python3 ${hooksDir}/timeline.py record apply-done --change-dir ${changeDir} --note "blocked=${blocked.length} blocking=${blocking.length}"\`，最后按第 0 项再提交一次飞行记录。返回 final 的 JSON。`,
  { label: retry ? 'final-gate:retry' : 'final-gate', schema: GATE, model: models.integrator, effort: efforts.integrator, ...typed('integrator') })
  .catch(() => null)
let final = await callFinal(false)
if (!final) final = await callFinal(true)
if (!final) blocked.push({ slice: 'final', kind: 'infra', reason: 'final-gate 未返回（已重派一次）' })

return { change, models, efforts, slices: results, blocked, blocking, deferred, fix, final, waves: wavesOut }
