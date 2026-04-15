# 模块: data.glossary

## 职责

- 存储运行时使用的 `中文 -> 英文` 术语映射
- 为查询理解层提供术语对齐输入
- 为 `/api/v1/glossary` 接口提供展示数据来源

## 行为规范

- 文件格式固定为 UTF-8 JSON，对象键为中文术语，值为英文术语。
- 当用户指定 xlsx 为唯一来源时，`data/glossary.json` 由 xlsx 直接重建，不保留旧 JSON 中未出现在 xlsx 的历史词条。
- xlsx 内存在重复中文词条时，按表内后出现记录覆盖前值，保证转换结果确定。
- 数据文件更新后不需要改动 `server/deps.py`，运行时会继续按原路径读取。

## 依赖关系

- 依赖 `server/config.py` 中的 `glossary_path` 配置
- 依赖 `server/deps.py` 中的 `get_glossary()` 在运行时加载
- 被 `server/core/query_understanding.py` 和 `server/api/v1/glossary.py` 消费
