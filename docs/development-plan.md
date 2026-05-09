# 音乐混音 / 母带质量分析 Web 工具开发计划

日期：2026-05-09

## 1. 目标

做一个可部署在 Linux VM 上的 Web 工具，用户上传 `mp3`、`wav` 或 `flac` 音频后，系统自动分析歌曲的混音与母带质量，并给出可读的指标、图表、综合判断和修改建议。

界面风格参考用户提供的截图：深色背景、清晰的评分摘要、按问题维度折叠的“建议变更”列表。最终产品应像一个实际可用的分析台，而不是只输出一堆技术数字。

这个工具不会宣称“自动判断艺术好坏”。它会把主观审美问题转成一组可解释的工程与感知指标，例如响度、动态、频谱平衡、相位、立体声、削波、噪声、低频管理、瞬态、平台归一化影响等，并明确给出指标依据和置信度。

## 2. 已知环境

### 2.1 本地开发目录

项目目录：

```text
/Users/xiyang/code/music-analysis
```

当前仓库为空，适合从零搭建项目结构。

### 2.2 测试音频目录

后续需要使用这里的本地音频进行测试：

```text
/Users/xiyang/Music/网易云音乐
```

初步检查到目录下有大量 `flac` 文件，也有少量 `mp3` 文件。测试时只抽样使用，不把用户音乐文件提交进仓库。

### 2.3 Linux VM

部署目标记录在：

```text
/Users/xiyang/code/wangyin_configs/truenas/vm.md
```

关键部署信息：

- 主机：`192.168.2.10`
- 用户：`wangyin`
- 系统：Debian VM
- 资源：约 8 GiB 内存、12 个 vCPU 线程、约 240 GiB 可用磁盘
- 已有服务：
  - Jellyfin: `http://192.168.2.10:8096/web/`
  - SubConverter: `http://192.168.2.10:25500`
  - 静态规则服务：`http://192.168.2.10:25501`

新服务应避免占用这些端口。计划默认使用 `8018`：

```text
http://192.168.2.10:8018
```

凭据和 sudo 方式沿用 `vm.md`，本计划不重复写入密码。

## 3. 产品范围

### 3.1 MVP 必须完成

1. 支持上传 `mp3`、`wav`、`flac`。
2. 后端解码并分析完整歌曲。
3. 输出综合评分、问题等级、指标详情和建议变更。
4. 展示至少这些维度：
   - 响度 / 母带目标
   - 动态范围
   - 削波 / 真峰值风险
   - 立体声声场
   - 相位与单声道兼容性
   - 频谱 / 音色平衡
   - 低频控制
   - 高频刺耳度 / 齿音风险
   - 噪声底与静音边界
   - DC 偏移
   - 文件技术信息
5. 前端提供清晰的上传、分析中、结果、错误状态。
6. 部署到 Debian VM，可以从局域网访问。
7. 用 `/Users/xiyang/Music/网易云音乐` 中的若干真实歌曲完成测试，并记录测试报告。

### 3.2 非 MVP 增强项

这些不阻塞第一版，但架构上要留位置：

- 多曲对比，例如同一首歌不同版本的母带比较。
- 风格 / 曲风预设阈值，例如流行、摇滚、古典、电子、ACG、播客。
- 更昂贵的源分离分析，例如人声、鼓、贝斯、伴奏分离后分别检查遮蔽和动态。
- 用户可保存历史报告。
- 导出 PDF / JSON 报告。
- 批量分析目录。

## 4. 技术方案

### 4.1 总体架构

计划使用单仓库、前后端分离开发、单容器部署：

```text
music-analysis/
  backend/
    app/
      main.py
      analyzer/
      scoring/
      reports/
    tests/
    pyproject.toml
  frontend/
    src/
    package.json
    vite.config.ts
  deploy/
    Dockerfile
    docker-compose.yml
    music-analysis.service optional
  scripts/
    analyze_file.py
    deploy_vm.sh
    sample_test.sh
  docs/
    development-plan.md
    deployment.md
    test-report.md
```

后端用 FastAPI 提供 API 和静态文件服务。前端用 React + TypeScript + Vite 构建，构建后的静态文件由后端容器一起提供。这样部署到 VM 时只需要启动一个服务。

### 4.2 后端

建议技术栈：

- Python 3.11+
- FastAPI
- Uvicorn
- NumPy / SciPy
- librosa
- soundfile
- pyloudnorm
- ffmpeg / ffprobe
- pydantic
- pytest

核心 API：

```text
GET  /healthz
POST /api/analyze
GET  /api/jobs/{job_id}
GET  /api/reports/{report_id}
GET  /api/reports/{report_id}/json
```

MVP 可以先用 FastAPI BackgroundTasks 或轻量线程池实现异步任务。若后续加入批量分析或源分离，再升级为 Redis + RQ / Celery。

上传文件策略：

- 只允许 `audio/mpeg`、`audio/wav`、`audio/flac` 以及对应扩展名。
- 文件名不可信，统一生成内部 UUID。
- 单文件大小默认限制先设为 `300 MB`，可通过环境变量调整。
- 分析完成后保留报告 JSON，上传原文件按配置清理。

### 4.3 音频处理流程

每个上传文件进入以下 pipeline：

1. `ffprobe` 读取元数据：
   - 容器格式
   - 编码格式
   - 采样率
   - 声道数
   - 位深 / bitrate
   - 时长
2. `ffmpeg` 解码为统一 PCM 流：
   - 分析用 `float32`
   - 保留原采样率用于峰值、频谱等指标
   - 需要时生成 48 kHz 版本用于部分统一窗口分析
3. 预处理：
   - 统一为二维数组：`samples x channels`
   - 对单声道文件做兼容处理
   - 去除 NaN / Inf
   - 记录首尾静音长度，但不擅自裁剪用于主分析
4. 计算指标。
5. 将指标输入评分器。
6. 生成建议文本、严重程度、置信度和图表数据。
7. 输出结构化 JSON。

## 5. 分析指标体系

### 5.1 综合评分

综合评分不直接等于“音乐好听程度”。它是技术风险评分，建议分为：

- `90-100`: 技术上很稳，只有轻微优化空间
- `75-89`: 整体可发布，有一些可检查点
- `60-74`: 有明显混音 / 母带问题
- `40-59`: 多项指标风险较高
- `<40`: 技术问题严重，建议回到混音或母带阶段

每个维度给出：

- 分数
- 严重程度：`info` / `minor` / `moderate` / `major`
- 关键指标
- 一句话结论
- 可展开解释
- 建议操作
- 置信度

### 5.2 响度与母带

指标：

- Integrated LUFS
- Momentary LUFS
- Short-term LUFS
- Loudness Range, LRA
- True Peak dBTP
- Sample Peak dBFS
- RMS
- 平台归一化预估，例如以 `-14 LUFS` 为参考估算 Spotify / YouTube 等平台可能下调多少 dB

判断：

- 过响：LUFS 太高且 True Peak 接近或超过 `-1 dBTP`
- 过轻：LUFS 过低但不是古典 / 环境类素材
- 平台下调：例如会被流媒体下调 `> 5 dB`
- 峰值余量不足：True Peak 高于 `-1 dBTP`

### 5.3 动态范围与压缩

指标：

- Crest Factor
- PLR, Peak to Loudness Ratio
- 窗口 RMS 分布
- 动态范围代理指标
- 短时响度变化
- 瞬态密度和瞬态被压扁风险

判断：

- 动态过窄，可能过度限制器 / 压缩。
- 动态过宽，可能导致听感忽大忽小。
- 副歌、高潮部分是否长期贴近峰值。

### 5.4 削波、失真与峰值风险

指标：

- Sample clipping count
- 连续削波片段数量
- Flat-top 波形检测
- True Peak / inter-sample peak 风险
- 峰值分布

判断：

- 出现明显数字削波。
- 可能有过强限制器造成的平顶。
- 上传到有损平台后可能产生额外超峰。

### 5.5 频谱与音色平衡

指标：

- 全曲平均频谱
- 分段频谱
- Octave / third-octave 频带能量
- Tonal tilt
- Sub bass: `20-60 Hz`
- Bass: `60-120 Hz`
- Low-mid mud: `150-500 Hz`
- Presence / harshness: `2-5 kHz`
- Sibilance: `5-9 kHz`
- Air: `10-16 kHz`
- 高频滚降和编码截止风险

判断：

- 低频过多或过少。
- 中低频浑浊。
- 2-5 kHz 过多导致刺耳。
- 5-9 kHz 齿音风险。
- 高频过暗或过亮。
- MP3 源可能存在明显低码率截止。

### 5.6 立体声、声场与相位

指标：

- L/R RMS 差异
- L/R 峰值差异
- Mid / Side 能量比例
- 频段化 stereo width
- Pearson correlation
- 负相关时间占比
- Mono fold-down 后响度变化
- 低频 Side 能量比例

判断：

- 声像偏左 / 偏右。
- 声场过窄或过宽。
- 低频太宽，可能影响黑胶、俱乐部系统或单声道播放。
- 单声道折叠后重要内容被抵消。
- 相位负相关过多。

### 5.7 噪声、静音与技术卫生

指标：

- 开头静音长度
- 结尾静音长度
- 静音段噪声底
- DC offset
- 50 / 60 Hz hum 风险
- 点击 / 爆音候选点
- 文件采样率、声道数、位深、码率

判断：

- 首尾没有合理留白或留白太长。
- 噪声底异常。
- 存在 DC 偏移。
- 可疑电源嗡声。
- 可疑点击 / 爆音。

### 5.8 清晰度与遮蔽代理指标

MVP 不做昂贵的源分离，但可以做代理判断：

- 频带能量是否长期堆积在 `150-500 Hz`。
- 低中频和人声存在感频段的相对比例。
- 分段谱质心、谱平坦度、谱通量。
- 复杂段落中高频瞬态是否被压制。

增强版可加入 Demucs / spleeter 类源分离，但这会显著增加 CPU、磁盘和模型依赖，不放入第一版上线阻塞项。

## 6. 前端设计

### 6.1 页面结构

首屏直接是工具，不做营销落地页：

1. 顶部标题与小型状态区。
2. 上传区：
   - 拖拽上传
   - 文件格式提示
   - 文件大小提示
3. 分析进度：
   - 上传中
   - 解码中
   - 计算指标中
   - 生成报告中
4. 结果摘要：
   - 综合评分
   - 发布风险等级
   - 一句话结论
   - 平台响度预估
5. 指标卡片：
   - 响度
   - 动态
   - 峰值
   - 频谱
   - 立体声
   - 相位
   - 噪声
6. 图表：
   - 波形概览
   - 响度随时间变化
   - 频谱 / 频带能量
   - 立体声相关性
7. “建议变更”折叠列表：
   - 类似截图中的条目样式
   - 每条显示问题名、短结论、严重程度
   - 展开后显示依据、数值和处理建议

### 6.2 UI 风格

- 深色工作台风格。
- 主色可以使用深蓝灰底、粉色 / 紫粉作为强调色，但避免整页单一紫色。
- 卡片圆角控制在 8px 左右。
- 重点不是装饰，而是让工程指标容易读。
- 移动端至少可正常上传和查看报告。

### 6.3 图表实现

优先使用 ECharts 或 Recharts。若依赖过重，MVP 可先用 Canvas 实现波形和简单频谱，后续再替换。

## 7. 评分与建议生成

### 7.1 评分器

评分器应与指标计算分离：

```text
raw metrics -> normalized metric scores -> category scores -> overall score -> recommendations
```

阈值不要硬编码散落在分析代码中。建议集中在：

```text
backend/app/scoring/thresholds.py
```

或后续改为：

```text
backend/app/scoring/profiles/default.yaml
```

### 7.2 建议文本

建议文本用模板生成，避免含糊的“听起来不好”。例如：

```text
检测到 Integrated LUFS 为 -7.1 LUFS，True Peak 为 -0.2 dBTP。
如果目标是常见流媒体发布，平台可能会将整体响度下调约 6.9 dB。
建议降低限制器输入或目标响度，并把 ceiling 调整到 -1.0 dBTP 附近。
```

每条建议应包含：

- 发生了什么
- 为什么可能是问题
- 可以尝试什么
- 这个判断的置信度

## 8. 数据与隐私

- 上传文件默认只在服务器本地临时存储。
- 报告 JSON 可保留，原始音频可配置自动删除。
- 不上传第三方服务。
- 测试使用的本地音乐文件不进入 Git。
- 日志不记录完整本地源文件路径，只记录内部 job id 和必要错误。

## 9. 开发阶段

### 阶段 0：项目初始化

产出：

- 后端 FastAPI 骨架
- 前端 Vite + React + TypeScript 骨架
- Dockerfile / docker-compose 初版
- 基础 README

验收：

- 本地能启动后端。
- 前端能访问。
- `/healthz` 返回正常。

### 阶段 1：音频解码与基础指标

产出：

- `ffprobe` 元数据读取
- `ffmpeg` 解码
- LUFS / true peak / sample peak / RMS / duration / channels / sample rate
- CLI 脚本 `scripts/analyze_file.py`

验收：

- 能分析本地 `mp3`、`wav`、`flac`。
- 对错误文件给出明确错误。
- 生成稳定 JSON。

### 阶段 2：扩展混音质量指标

产出：

- 动态范围指标
- 削波 / 平顶检测
- 频谱平衡指标
- stereo width / correlation / mono compatibility
- DC offset / silence / noise floor 初版

验收：

- 每个指标有单元测试或合成音频测试。
- JSON 中包含分维度结果和图表数据。

### 阶段 3：评分与建议系统

产出：

- 分类评分
- 综合评分
- 严重程度
- 建议生成
- 流媒体响度下调预估

验收：

- 至少 10 类建议能被触发。
- 建议中包含具体数值和建议动作。

### 阶段 4：前端结果页

产出：

- 上传组件
- 分析状态
- 结果摘要
- 指标卡片
- 图表
- “建议变更”折叠列表
- 错误状态

验收：

- 桌面和移动端不发生文字溢出或控件重叠。
- 上传真实音频后能看到完整报告。

### 阶段 5：真实音频测试

产出：

- 从 `/Users/xiyang/Music/网易云音乐` 抽样测试：
  - 至少 3 个 `flac`
  - 至少 1 个 `mp3`
  - 若目录中有 `wav` 则加入 1 个 `wav`；没有则用测试夹生成一个 WAV 合成样本
- 记录：
  - 文件名
  - 格式
  - 时长
  - 分析耗时
  - 是否成功
  - 关键指标
  - 发现的问题

验收：

- 生成 `docs/test-report.md`。
- 所有抽样文件可以完成分析。

### 阶段 6：Linux VM 部署

产出：

- VM 预检脚本
- Docker 镜像构建
- docker-compose 启动
- 服务暴露在 `8018`
- 部署文档

部署优先级：

1. 优先使用 Docker Compose，保证依赖如 `ffmpeg`、`libsndfile`、Python 包可重复安装。
2. 如果 VM 没有 Docker，再选择：
   - 安装 Docker / Compose 插件；或
   - 使用 Python venv + systemd 的非容器部署方式。

验收：

- `curl http://192.168.2.10:8018/healthz` 正常。
- 局域网浏览器可以打开页面。
- 上传一首测试音频可以完成分析。

### 阶段 7：收尾文档

产出：

- README
- 部署文档
- 测试报告
- 已知限制
- 后续路线图

## 10. 测试计划

### 10.1 单元测试

使用合成音频验证：

- 正弦波峰值
- 已知 RMS
- 静音文件
- 单声道文件
- 双声道相位反转文件
- 人为削波文件
- DC offset 文件
- 高频滚降文件

### 10.2 集成测试

使用真实文件验证：

```text
/Users/xiyang/Music/网易云音乐/*.flac
/Users/xiyang/Music/网易云音乐/*.mp3
```

测试方式：

- CLI 直接分析文件。
- API 上传分析。
- 前端上传分析。

### 10.3 UI 测试

- 本地启动 Web 服务。
- 用浏览器验证桌面宽度。
- 验证移动端宽度。
- 检查图表非空、文字不重叠、折叠项可操作。

### 10.4 部署验收

- SSH 到 VM 检查服务状态。
- 检查端口监听。
- 从本地访问健康检查。
- 上传真实音频完成分析。

## 11. 风险与应对

### 11.1 “混音质量”带有主观性

应对：

- 报告中明确这是工程和感知风险分析。
- 所有建议都给出指标依据。
- 不使用绝对化措辞。

### 11.2 不同曲风阈值不同

应对：

- MVP 使用通用发布阈值。
- 报告中展示置信度。
- 预留曲风 profile。

### 11.3 大文件分析慢

应对：

- 后端采用任务式分析。
- 图表数据降采样。
- 设置上传大小限制。
- 对长文件记录分析进度。

### 11.4 源分离很耗资源

应对：

- MVP 不把源分离作为必需项。
- 用频谱和动态代理指标先覆盖大部分可操作建议。

### 11.5 Linux VM 依赖状态未知

应对：

- 先做部署预检。
- Docker Compose 优先。
- 准备 systemd + venv fallback。

## 12. 初版完成标准

初版完成时应满足：

1. 本地仓库包含完整源码、测试、部署文件和文档。
2. 本地可以分析真实 `mp3`、`wav`、`flac`。
3. Web 页面可以上传音频并展示完整报告。
4. 至少覆盖 10 个混音 / 母带评估维度。
5. `docs/test-report.md` 记录了用网易云音乐目录样本的测试结果。
6. 工具部署在 Debian VM。
7. 局域网可访问：

```text
http://192.168.2.10:8018
```

8. 最终回复用户时说明：
   - 本地如何启动
   - VM 上如何访问
   - 测试了哪些音频
   - 已知限制

## 13. 建议实施顺序

建议按以下顺序执行，避免 UI 已经做好但分析结果不可用：

1. 后端骨架和 CLI。
2. 音频指标计算。
3. 评分与建议。
4. 前端展示。
5. 本地真实音频测试。
6. Docker 化。
7. VM 部署。
8. 远端验收和文档整理。

## 14. 暂定默认参数

这些参数可以在实现中微调：

```text
服务端口: 8018
上传大小限制: 300 MB
报告保留目录: ./data/reports
上传缓存目录: ./data/uploads
图表最大点数: 1200
分析目标响度参考: -14 LUFS
建议 True Peak ceiling: -1.0 dBTP
低频单声道关注范围: 20-120 Hz
相位负相关警戒线: correlation < -0.1
```

## 15. 计划确认后要做的第一批文件

确认计划后，先创建这些文件：

```text
README.md
backend/pyproject.toml
backend/app/main.py
backend/app/analyzer/pipeline.py
backend/app/analyzer/metrics.py
backend/app/scoring/scorer.py
backend/tests/test_synthetic_audio.py
frontend/package.json
frontend/src/App.tsx
frontend/src/styles.css
deploy/Dockerfile
deploy/docker-compose.yml
scripts/analyze_file.py
```

