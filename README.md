# PeekTodo

贴在屏幕右边缘的待办面板。鼠标贴到主屏最右边，滑出你今天要做的事；鼠标离开自动收回。
点一下可以钉住，拖角落能改大小。常驻托盘，平时不抢焦点，可开机自启。

[English](README.en.md)

![面板](docs/screenshot-panel.png)

## 它解决什么

你有周计划，但不会为了看一眼今天该干什么去打开幕布或翻笔记。
PeekTodo 把它贴在屏幕边缘，抬一下鼠标就能看到。

**数据源**：本地 Markdown（`- [ ]` 列表）或幕布文档。
**只读**：不修改你的文件；面板上的勾选只存在本地，7 天后自动失效。

## 快速开始

```bash
git clone https://github.com/ConstVain/PeekTodo.git
cd PeekTodo
pip install .
peektodo
```

也可以不安装，直接从源码跑：

```bash
pip install -r requirements.txt
python -m peek_todo
```

首次运行会打开设置面板：选数据源 → 在结构树里点一个节点当根 → 选模式 → 保存。没有现成文档的话，点「新建 Markdown 文档」，会生成一份带示例内容的模板并直接打开给你改。之后随时可以从托盘菜单「设置…」再打开，刷新间隔、强调色、开机自启、桌面快捷方式都在那里改。

![设置](docs/screenshot-settings.png)

之后（在终端里运行时，PeekTodo 会自己转成后台进程，关掉终端不影响）：

```bash
peektodo                    # 正常使用（托盘常驻）
peektodo --setup            # 打开设置面板
peektodo --force-shown      # 强制展开，调样式用
peektodo --force            # 已有实例占着时强制再开一个
peektodo --doctor           # 命令行体检（不转后台，直接看输出）
peektodo --no-detach        # 留在前台，方便看日志
```

不想开终端就双击仓库里的 `start.cmd`，它会用 `pythonw` 在后台启动。

装成包之后，配置放在 `%APPDATA%\PeekTodo\`；直接跑源码时配置就在仓库根目录（便携）。

### 桌面快捷方式

首次保存设置时会自动在桌面放一个 `PeekTodo` 快捷方式（带应用图标，点开就是后台常驻，没有黑框）。不想要就在设置面板取消「桌面快捷方式」，下次保存会删掉。

想手动补一个：

```bash
powershell -ExecutionPolicy Bypass -File tools\install_shortcut.ps1
```

### 更新

已经装过旧版本的话，**进到当初 clone 的那个目录**里更新，不要再 clone 一次：

```bash
cd PeekTodo
git pull
python -m pip install --no-build-isolation --force-reinstall .   # 当初用 pip install -e . 装的就不用这行
```

然后从托盘图标退出、重新启动。`config.json` 和 `.state.json` 都在 `.gitignore` 里，更新不会动你的配置和勾选状态。

## 怎么用

| 操作 | 结果 |
|---|---|
| 鼠标贴屏幕最右边 | 面板滑出 |
| 鼠标移开 | 自动收回 |
| **点一下面板** | 钉住：拿到焦点，鼠标移开也不收回 |
| **拖左上角 / 左下角** | 调整面板大小，文字同步缩放；拖到面板外面也不会收回 |
| 点勾选框 | 勾选/取消（只改面板本地状态，不动源文件） |
| 双击文字 | 用默认程序打开源文件 |
| 离面板较远处单击 / Esc | 解除钉住并收回 |

大小拖过之后会记住（写进 `config.json` 的 `panel.width` / `panel.height`），下次启动还是这个尺寸。

## 三种模式

| 模式 | 根的直接子节点 | 面板怎么显示 | 适合 |
|---|---|---|---|
| **周计划** | 时段（`周一下午`） | 上方当前时段，下方今天 | 按周排课/排班的计划 |
| **截止日** | 日期（`11月2日`） | 上方逾期 + 今天到期，下方「接下来」 | DDL、作业、交付 |
| **备忘单** | 直接是事项（没有分组） | 全部常驻，不做任何筛选 | 本周计划、长期提醒 |

前两种的结构一样（根 → 分组 → 事项），区别只在于**分组标题怎么解读**：当作"一周里的某个时段"，还是当作"某个日期"。备忘单没有分组，根下面就是清单。

<table>
<tr>
<td width="33%"><b>周计划</b>：上方当前时段，下方今天<br><img src="docs/screenshot-panel.png"></td>
<td width="33%"><b>截止日</b>：逾期标红，其余按日期排<br><img src="docs/screenshot-due.png"></td>
<td width="33%"><b>备忘单</b>：一张常驻清单<br><img src="docs/screenshot-memo.png"></td>
</tr>
</table>

日期支持这些写法：`11月2日`、`11月3号`、`2026-11-02`、`11/2`、`今天`、`明天`、`后天`。
时段支持：`周一下午`、`星期二上午`、`礼拜三`、`周7 早上`，也可以在 `config.json` 的 `vocabulary` 里加别名。

选错模式不会给你空面板：周计划模式下如果标题全是日期，会提示「也许该选截止日」；结构是平铺清单时会自动降级成备忘单。

## 为什么不用固定语法

不同人的写法差别很大（「周一下午」/「礼拜一下午」/「下午」）。PeekTodo 不要求你改文档：

- 时间词靠可配置词表识别（见 `config.json` 的 `vocabulary`）
- 认不出来的标题**照样显示**，只是不参与时段筛选，并在底部标出来
- `--doctor` 把"程序看懂了什么"直接打出来，认错了一眼能看见

```
来源   docs/sample-plan.md
根     周计划
模式   周计划
──────────────────────────────────────────────
✓ 周一下午                  周一下午  ·  4 条（2 层）
✓ 周二上午                  周二上午  ·  2 条
! 待定                      未识别时间  ·  1 条
──────────────────────────────────────────────
事项 8 条，其中已完成 1 条
```

## 目录

```
peek_todo/
├─ model.py         Node / Task / Group
├─ vocabulary.py    时段与日期识别（词表可配）
├─ structure.py     根节点 + 三种模式
├─ selection.py     按当前时间切片
├─ state.py         本地勾选（不碰源文件）
├─ edge.py          贴边判定
├─ report.py        识别报告
├─ doctor.py        命令行体检
├─ autostart.py     开机自启（HKCU Run）
├─ shortcut.py      桌面快捷方式
├─ opener.py        打开数据源
├─ template.py      「新建 Markdown 文档」的模板
├─ win32.py         pywin32 加载兜底、窗口样式、按键状态
├─ app.py           入口：窗口、托盘、轮询
├─ assets/          托盘图标与应用图标
├─ sources/
│  ├─ markdown.py   标题 + 列表项
│  └─ mubu.py       幕布本地备份
└─ ui/
   ├─ panel.py      面板（含拖拽缩放）
   └─ settings.py   设置面板（首次运行也用它）
```

## 开发

```bash
python -m pytest tests -q
verify.cmd            # 测试 + 两个数据源的体检
```

## 说明与限制

- **只读**：不写入 Markdown 或幕布文档。面板上的勾选是本地的，不改变源。
- **不联网**：没有任何网络请求。
- **幕布源**读取桌面端本地缓存，属于非公开格式，客户端升级可能失效；失效时保留上次数据并提示。
- 仅支持 Windows 10/11（依赖 Win32 的 `WS_EX_NOACTIVATE` 与光标轮询）。

## 许可证

GPL-3.0，见 [LICENSE](LICENSE)。因为依赖 PyQt5（GPL/商业双许可），整个项目按 GPL 发布。
