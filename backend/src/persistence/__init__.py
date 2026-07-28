"""
RELEASE 持久化与发布质量域（docs/15-persistence-release-quality）

模块划分：
- constants        产品常量与 RELEASE reason_code 注册表
- paths            RULE-RELEASE-001/054 用户数据根目录与布局
- database         RULE-RELEASE-003/004/007 SQLite 连接策略
- schema           app.sqlite3 / world.sqlite3 DDL（DES-RELEASE-001/005/006/008）
- migrations       DOC-RELEASE-002 只前向迁移
- event_log        RULE-RELEASE-017..019 追加式事件日志
- zstd_codec       纯 Python zstd 帧（raw/RLE 块）编解码
- snapshots        DOC-RELEASE-003 Snapshot 生成/加载/保留
- replay           RULE-RELEASE-023..024 确定性重放与 upcaster
- saves            DOC-RELEASE-004 自动恢复点与手动槽位
- branch           RULE-RELEASE-028..029 branch-on-load
- worlds           DOC-RELEASE-005 世界注册表生命周期
- transfer         DOC-RELEASE-005 世界导出/导入
- recovery         DOC-RELEASE-006 备份、恢复链与分诊阶梯
- settings         DOC-RELEASE-007 非敏感配置白名单
- secret_scan      RULE-RELEASE-075 共享脱敏扫描器
- diagnostics_pkg  DOC-RELEASE-010 诊断包
- launcher         DOC-RELEASE-008 instance.json 与健康轮询
- release_manifest DOC-RELEASE-009 发布包清单与黑名单
- gates            DOC-RELEASE-011/012 量化门槛与 G9 清单
"""
