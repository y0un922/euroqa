"""Retrieval recall evaluation sandbox.

完全隔离的检索召回评测模块。所有评测代码、转换脚本、trace 工具、实验配置
与结果文件位于本目录下，与 server/ pipeline/ tests/eval/ 等业务模块零代码侵入。

删除整个目录后 repo 任何业务行为不变；不会被 server 或 pipeline 模块 import。

入口：
    convert:  python -m experiments.retrieval_eval.dataset.convert ...
    baseline: python experiments/retrieval_eval/run_baseline.py
    triage:   python experiments/retrieval_eval/triage.py <results.json>
    verify:   bash experiments/retrieval_eval/verify_isolation.sh
"""
