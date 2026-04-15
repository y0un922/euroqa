# Phase 1: 引用对象模型与离线引用图

## 目标

把 chunk 升级为可寻址规范对象，并在离线阶段生成引用边。

## 任务清单

- [x] **P1-T1**: 扩展内部引用抽取
  - 验收：支持 `Table/Figure/Expression/Clause`

- [x] **P1-T2**: 建立规范对象标识
  - 验收：对象有稳定 `object_id/object_label/object_type`

- [x] **P1-T3**: 生成引用边
  - 验收：主条款能直接指向被引对象

- [x] **P1-T4**: 扩展索引字段
  - 验收：ES 可按对象字段精确检索

- [x] **P1-T5**: 重建与校验索引脚本
  - 验收：可输出 unresolved refs 报告

## Notes

- 这阶段是全链路基础，不要跳过
- 若对象模型不稳定，后续在线 resolver 和 generation 都会反复返工
- 已完成实现：
  - `extract_cross_refs()` 新增 `Table/Figure/Expression/Clause` 抽取
  - `ChunkMetadata` 新增 `object_* / ref_*` 字段
  - text/table chunk 已生成稳定对象标识和引用对象 ID
  - ES mapping 已补对象字段
  - `scripts/rebuild-indexes.sh` 已输出 unresolved refs 统计
- 已验证：
  - `tests/pipeline/test_structure.py`
  - `tests/pipeline/test_chunk.py`
  - `tests/server/test_retrieval.py`
  - `tests/server/test_generation.py`
