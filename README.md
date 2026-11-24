# 实验室设备预约系统

软件工程课程设计的课程项目：一个高校实验室设备预约系统。桌面端用 PyQt6，移动端用 Flask + H5，
数据存放在本地 SQLite 中，代码按 MVC 分层。

项目围绕“预约”这条主线展开：学生查设备、提交预约，教师和管理员分级审核，到场签到后联动门禁与电源；
此外还做了候补队列、信用分、统计图表等辅助功能。门禁和 IoT 数据是模拟的，人脸识别在缺少依赖时
会自动回退到手动签到，不影响主流程。

## 技术栈

| 层级 | 技术选型 |
| --- | --- |
| 桌面 GUI 视图层 | PyQt6（QMainWindow + QStackedWidget + QTableWidget + QSS 微信风格） |
| 移动端 | Flask REST API + H5 响应式页面（微信小程序风格） |
| 业务语言 | Python 3.10+ |
| 数据库 | SQLite（文件型，无需安装服务） |
| 密码加密 | bcrypt（禁止明文） |
| AI 推荐 | 本地启发式算法（无需联网 / 密钥） |
| 人脸识别 | OpenCV + face_recognition（缺库时自动回退手动签到） |
| 图表 / 二维码 | matplotlib、qrcode[pil] |
| 报表导出 | pandas → CSV |
| 测试 | unittest + coverage |

## 项目结构（MVC 分层）

```
lab_equipment_booking/
├── main.py                    # 程序入口（加载 QSS）
├── config.py                  # 全局配置（含超管密文解析）
├── requirements.txt
├── db/
│   ├── init_db.py             # 建表 + 迁移 + 初始化超管 + 种子数据
│   ├── base_model.py          # DAO 基类（连接/游标/事务）
│   ├── admin_secret.txt       # 超管初始密码密文（已 gitignore，仅开发人员可见）
│   └── device_booking.db      # 运行时自动创建
├── model/                     # 数据访问层（DAO，含 campus/sign_in/credit_log）
├── controller/                # 业务控制层（预约/签到/物联/信用等）
├── view/                      # 视图层（登录/学生/管理员/超管/导师 + 组件 + QSS + 图表）
├── server/                    # Flask 移动端（app.py + templates/index.html）
├── utils/                     # 工具（加密/时间/校验/导出/备份/常量/AI/人脸/物联模拟）
├── test/                      # 单元测试 + 集成测试（58 个用例）
├── code/                      # 实验六核心模块（lab_reservation + 39 个单元测试）
└── hello.py                   # 实验一 Hello World 验证脚本
```

分层约束：`View 只调用 Controller`，`Controller 只调用 Model-DAO`，`Model-DAO 直接访问 SQLite`。

## 运行方式

```bash
cd lab_equipment_booking
pip install -r requirements.txt   # PyQt6 / bcrypt / pandas / flask / matplotlib / qrcode
python main.py                     # 启动桌面端
python server/app.py               # 启动移动端（手机访问 http://<本机IP>:5000）
```

首次运行自动创建数据库、迁移旧库、初始化种子数据，无需额外配置。

## 预置账号

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 超级管理员 | admin | 随机生成，见 `db/admin_secret.txt`（UI 不展示，仅开发人员可见） |
| 实验室管理员 / 学生 / 教师 | 在界面「注册」自助创建，或由超管在「账号管理」创建 | — |

## 功能清单

- **学生**：注册登录、记住账号、浏览/搜索设备、查看剩余可约数量、提交预约（即时/审批/周期）、
  取消预约、日历视图（日/周/月）、人脸/手动签到、信用分查询、报修、公告、候补、站内消息、二维码查看
- **教师/导师**：审批型 / 周期型预约的一级审核（导师 → 管理员二级审批）
- **实验室管理员**：设备 CRUD（含数量与二维码）、校区筛选、预约审核（含多级审批）、标记完成/爽约、
  签到记录、门禁/电源联动、IoT 实时监控、统计图表、报修、公告、候补、报表导出
- **超级管理员**：账号管理（含教师角色）、黑名单、校区管理、系统参数、系统日志、统计图表、数据备份恢复

## 核心业务规则

1. **设备数量并发**：预约按「设备总量 vs 已占用数」判断冲突（`count_overlap >= total_count` 才算满），
   支持同型号多台设备并发预约，界面实时显示剩余可约数量。
2. **多重校验**：非过去时间、单次时长 ≤ 上限、设备非维修/报废、账号非黑名单、信用分 ≥ 阈值。
3. **多级审批**：审批型/周期型预约需导师先通过，再经管理员审核；即时预约仅管理员审核。
4. **预约状态机**：待审核 → 已通过/已驳回；待审核/已通过 → 已取消；已通过 → 已完成/爽约。
5. **爽约与信用分**：标记爽约累计次数 +1 并扣信用分（默认 20），达到阈值禁用账号；信用分不足禁止预约。
6. **签到与物联联动**：预约已通过且处于时段内可签到，签到后自动开对应实验室门禁、设备通电。
7. **AI 智能推荐**：本地启发式算法分析当日已预约区间，返回最优空闲时段（越早、缓冲越充裕越优先）。
8. **候补转正**：预约取消时，同设备同时段最早候补者自动转正为「待审核」预约并收到站内消息。
9. **密码安全**：bcrypt 哈希存储；超级管理员初始密码随机生成并写入 gitignore 的密文文件。

## 运行测试

```bash
cd lab_equipment_booking
python -m unittest discover -s test -t . -v     # 58 个用例
python -m coverage run --source=controller,model -m unittest discover -s test -t .
python -m coverage report -m
```

核心模块（实验六、实验八）可独立运行：

```bash
cd code
python main.py                                  # 演示完整预约闭环
python -m unittest discover -s tests -t . -v    # 39 个单元测试
```

## 开发说明

- 这是课程设计项目，代码优先保证分层清楚、业务规则可测试，没有按生产系统做并发和权限加固。
- 核心模块在 `code/`，不依赖 PyQt，可以单独运行和测试，便于在实验六、实验八中复用。
- 提交信息按 Conventional Commits 写，功能开发走 `feature/*` → `dev` → `main`。
- 开发环境是 Windows 11 + Python 3.12，其他平台未做完整验证。

## 说明

- 系统参数（预约最大时长、黑名单阈值、最低信用分）可在超管「系统参数」页实时修改。
- 人脸识别依赖 `opencv-python` / `face-recognition`（dlib），Windows 上可能安装失败；
  代码已做 ImportError 降级，缺失时自动回退手动签到，不影响主流程。
- 数据备份位于 `db/backup/` 目录。
