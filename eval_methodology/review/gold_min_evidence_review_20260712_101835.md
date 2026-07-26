# Gold 最小充分证据集人工复核 (20260712_101835)

范围：**全部题目**。任务 = 确认每题 E⁺ 是否为支持 claims 的最小充分集。
模型分歧题额外标 `[DISPUTED]`。

题数：31

## Q01: 请给出混凝土结构设计中相关作用荷载和材料的分项系数。
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (8): 35d57a7076d7fb05618f174c1dbfd86e, 35eb4a9edcf9e2ca53e5fe6a931e26ba, 54db97f8efccf4a8a44d81fbca24f2f8, 9688579d101aa7f2ccf09f7a2d24de51, b35b164167f2628cfed20b488ad96390, c020cd1200b8c315f905ae57a13974c4, c5d748c134cc7b672baf155137cf9c6a, e3fc1531ef96bcfc60bd9ebf677808e9
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 根据候选池中的 Eurocode 资料，混凝土结构设计常用分项系数可归纳如下：

- 承载能力极限状态（ULS）的典型作用分项系数：永久作用 γG = 1.35，可变作用 γQ = 1.50。具体组合中，EN 1990 式 (6.10a)/(6.10b) 对永久荷载、使用荷载和风荷载采用不同系数组合，例如永久+使用荷载可分别取 1.35G+1.05Q 或 1.25G+1.50Q；伴随可变作用还可能取 0.75。
- 材料分项系数：混凝土 γc = 1.50，钢筋 γs = 1.15。
- 正常使用极限状态（SLS）计算时，材料性能采用的分项系数通常为 1.0。

具体工程仍应结合所采用的设计组
  - claim `claim_1` [supported]: 承载能力极限状态设计中，永久作用的典型分项系数 γG 为 1.35。
    evidence: 54db97f8efccf4a8a44d81fbca24f2f8, 9688579d101aa7f2ccf09f7a2d24de51
  - claim `claim_2` [supported]: 承载能力极限状态设计中，可变作用的典型分项系数 γQ 为 1.50。
    evidence: 54db97f8efccf4a8a44d81fbca24f2f8, 9688579d101aa7f2ccf09f7a2d24de51
  - claim `claim_3` [supported]: 按 EN 1990 式 (6.10a)/(6.10b) 的典型 STR 组合，永久荷载、使用荷载和风荷载的系数会随主导作用变化，例如永久+使用荷载可取 1.35G+1.05Q 或 1.25G+1.50Q，伴随可变作用可取 0.75。
    evidence: 9688579d101aa7f2ccf09f7a2d24de51
  - claim `claim_4` [supported]: 混凝土的材料分项系数 γc 为 1.50。
    evidence: 35d57a7076d7fb05618f174c1dbfd86e, b35b164167f2628cfed20b488ad96390, c020cd1200b8c315f905ae57a13974c4
  - claim `claim_5` [supported]: 钢筋的材料分项系数 γs 为 1.15。
    evidence: 35d57a7076d7fb05618f174c1dbfd86e, b35b164167f2628cfed20b488ad96390, c020cd1200b8c315f905ae57a13974c4
  - claim `claim_6` [supported]: 正常使用极限状态计算中，材料性能的分项系数通常取 1.0。
    evidence: e3fc1531ef96bcfc60bd9ebf677808e9
  - claim `claim_7` [supported]: 分项系数的最终取值应结合相应国家附录确定。
    evidence: 35eb4a9edcf9e2ca53e5fe6a931e26ba, c5d748c134cc7b672baf155137cf9c6a
- [ ] 人工确认最小充分证据集

## Q02: 请给出混凝土材料的强度与变形的相关定义、相互关系及如何计算。
- status: needs_human_review
- gold_claim_status: mixed
- E⁺ (6): 344157c7debd304b2859e15bfcfddb29, 35d57a7076d7fb05618f174c1dbfd86e, 49f2adc76cde55a966f8dc1a9763c9cc, 7fcb7baf690f9f9e0d31b0eb93feda98, b1c56ada9b50bee627f7b881b5ff9d5e, b4d264f362ae3541f62c4717c1c5285d
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 候选池对该问题的覆盖不完整，只能给出以下有证据支持的内容：

1. 强度：混凝土强度等级以圆柱体特征抗压强度 fck 表示，并对应立方体特征抗压强度 fck,cube。例如，fck=25 MPa 对应 fck,cube=30 MPa，即 C25/30；表中还给出了 C12/15 至 C90/105 的对应关系。候选池未提供特征强度、平均强度和设计强度的完整定义及换算公式。

2. 变形：混凝土弹性变形通常用平均弹性模量 Ecm 表征。Ecm 定义为混凝土应力从 0 增至 0.4fcm 时的割线模量。其数值受混凝土组成、尤其是骨料弹性模量影响。规范表值以石英岩骨料为基准；石灰岩和砂岩骨料应分别降
  - claim `c1` [supported]: 混凝土强度等级以圆柱体特征抗压强度 fck 和相应的立方体特征抗压强度 fck,cube 表示。
    evidence: b4d264f362ae3541f62c4717c1c5285d
  - claim `c2` [supported]: fck=25 MPa 对应 fck,cube=30 MPa，即强度等级 C25/30。
    evidence: b4d264f362ae3541f62c4717c1c5285d, 35d57a7076d7fb05618f174c1dbfd86e
  - claim `c3` [supported]: 候选池给出了从 fck=12 MPa、fck,cube=15 MPa 到 fck=90 MPa、fck,cube=105 MPa 的强度对应关系。
    evidence: b4d264f362ae3541f62c4717c1c5285d
  - claim `c4` [supported]: 混凝土平均弹性模量 Ecm 是应力从 0 到 0.4fcm 区间的割线模量。
    evidence: b1c56ada9b50bee627f7b881b5ff9d5e
  - claim `c5` [supported]: 混凝土弹性变形显著取决于其组成，尤其是骨料。
    evidence: b1c56ada9b50bee627f7b881b5ff9d5e
  - claim `c6` [supported]: 规范中的 Ecm 表值以石英岩骨料混凝土为基准；石灰岩和砂岩骨料应分别降低 10% 和 30%，玄武岩骨料应提高 20%。
    evidence: b1c56ada9b50bee627f7b881b5ff9d5e
  - claim `c7` [supported]: 混凝土弹性模量与强度参数相关，因为 Ecm 的割线定义以 0.4fcm 为终点，但弹性模量还受骨料等组成因素影响。
    evidence: b1c56ada9b50bee627f7b881b5ff9d5e
  - claim `c8` [supported]: Ecm 随龄期的变化可根据龄期 t 时的 fcm(t)、长期 fcm 和 Ecm 进行估算。
    evidence: b1c56ada9b50bee627f7b881b5ff9d5e
  - claim `c9` [corpus_gap]: 候选池没有显示 Ecm 随龄期变化的完整计算公式。
    evidence: —
  - claim `c10` [supported]: 对于 fck=25 MPa，示例按 fctm=0.30fck^(2/3) 计算得到 fctm≈2.56 MPa。
    evidence: 35d57a7076d7fb05618f174c1dbfd86e
  - claim `c11` [supported]: 构件刚度计算通常可采用混凝土平均弹性模量和未开裂毛截面惯性矩；计算变形、收缩和沉降影响时，应采用与开裂截面相应的折减刚度。
    evidence: 344157c7debd304b2859e15bfcfddb29
  - claim `c12` [supported]: 钢筋混凝土裂缝计算中的平均应变差可由钢筋应力、混凝土有效抗拉强度、有效配筋率、模量比和钢筋弹性模量计算。
    evidence: 49f2adc76cde55a966f8dc1a9763c9cc, 7fcb7baf690f9f9e0d31b0eb93feda98
  - claim `c13` [corpus_gap]: 候选池足以完整定义并计算混凝土特征强度、平均强度、设计强度及其全部相互关系。
    evidence: —
  - claim `c14` [corpus_gap]: 候选池足以完整给出混凝土应力—应变曲线、峰值应变和极限压应变的定义与计算方法。
    evidence: —
  - claim `c15` [corpus_gap]: 候选池足以完整给出混凝土徐变和收缩变形的定义及计算方法。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q03: 有哪些因素会对混凝土的徐变与收缩产生影响?
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (4): 38aa169478df9a081effd396beb31679, ad4cdde0af53b6447694577452b5f413, bb3c322a3a0937199dce5ba0aedf29be, eb8cc418a1026d54d4c8fcd40f3bb009
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 根据候选池中的 Eurocode 2 条文，混凝土徐变与收缩的主要影响因素包括：环境湿度或气候条件、构件的尺寸与形状、构件温度以及混凝土组成。基本收缩还与水灰比及由此相关的混凝土强度有关。对于徐变，还需考虑首次加载时混凝土的龄期（成熟度），以及荷载的持续时间和大小；当加载时压应力较高时，还应考虑徐变的非线性发展。
  - claim `claim_1` [supported]: 环境湿度或气候条件会影响混凝土徐变与收缩。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009, 38aa169478df9a081effd396beb31679, bb3c322a3a0937199dce5ba0aedf29be, ad4cdde0af53b6447694577452b5f413
  - claim `claim_2` [supported]: 构件尺寸会影响混凝土徐变与收缩。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009, 38aa169478df9a081effd396beb31679
  - claim `claim_3` [supported]: 构件的尺寸和形状会影响干燥收缩的发展。
    evidence: bb3c322a3a0937199dce5ba0aedf29be, ad4cdde0af53b6447694577452b5f413
  - claim `claim_4` [supported]: 构件温度会影响干燥收缩的发展。
    evidence: bb3c322a3a0937199dce5ba0aedf29be, ad4cdde0af53b6447694577452b5f413
  - claim `claim_5` [supported]: 混凝土组成会影响混凝土徐变与收缩。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009, 38aa169478df9a081effd396beb31679
  - claim `claim_6` [supported]: 基本收缩与水灰比以及由此相关的混凝土强度有关。
    evidence: bb3c322a3a0937199dce5ba0aedf29be
  - claim `claim_7` [supported]: 首次施加荷载时混凝土的龄期或成熟度会影响徐变。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009, 38aa169478df9a081effd396beb31679
  - claim `claim_8` [supported]: 荷载的持续时间会影响混凝土徐变。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009
  - claim `claim_9` [supported]: 荷载或压应力的大小会影响混凝土徐变；较高压应力下需考虑徐变的非线性发展。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009, 38aa169478df9a081effd396beb31679
- [ ] 人工确认最小充分证据集

## Q04: 钢筋的主要特性有哪些?并给出相应总结。
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (2): 380bfaca75c912b0f5c414bd52e47e4f, d3dbb363af61cce1e53b23d1bd4b85de
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 按 Eurocode 2，钢筋的主要特性包括：屈服强度（或 0.2% 规定塑性延伸强度）、最大实际屈服强度、抗拉强度、延性（以最大荷载时伸长率及抗拉强度/屈服强度比表征）、弯曲性能、与混凝土的黏结性能、截面尺寸及其公差、疲劳强度和可焊性。对于焊接钢筋网和钢筋桁架，还应考虑剪切强度与焊点强度。新版 Eurocode 2 将强度等级、延性等级以及直径或规格列为设计至少需要明确的基本属性，并可据此确定屈服强度、强屈比、最大荷载时伸长率和疲劳 S-N 曲线。总结而言，钢筋性能可概括为强度、延性与变形能力、黏结和加工连接性能、几何规格以及疲劳性能；这些特性共同决定钢筋的承载能力、变形能力、与混凝土协同工
  - claim `claim_1` [supported]: 钢筋的主要强度特性包括屈服强度或0.2%规定塑性延伸强度。
    evidence: 380bfaca75c912b0f5c414bd52e47e4f, d3dbb363af61cce1e53b23d1bd4b85de
  - claim `claim_2` [supported]: 钢筋的性能还包括最大实际屈服强度和抗拉强度。
    evidence: 380bfaca75c912b0f5c414bd52e47e4f
  - claim `claim_3` [supported]: 钢筋延性可由最大荷载时伸长率以及抗拉强度与屈服强度之比表征。
    evidence: 380bfaca75c912b0f5c414bd52e47e4f, d3dbb363af61cce1e53b23d1bd4b85de
  - claim `claim_4` [supported]: 钢筋的弯曲性能是其规定特性之一。
    evidence: 380bfaca75c912b0f5c414bd52e47e4f
  - claim `claim_5` [supported]: 钢筋与混凝土之间的黏结性能是钢筋的主要特性之一。
    evidence: 380bfaca75c912b0f5c414bd52e47e4f
  - claim `claim_6` [supported]: 钢筋的截面尺寸及尺寸公差属于需要规定的特性。
    evidence: 380bfaca75c912b0f5c414bd52e47e4f
  - claim `claim_7` [supported]: 疲劳强度是钢筋的重要性能，可通过疲劳S-N曲线描述。
    evidence: 380bfaca75c912b0f5c414bd52e47e4f, d3dbb363af61cce1e53b23d1bd4b85de
  - claim `claim_8` [supported]: 可焊性是钢筋的规定特性之一。
    evidence: 380bfaca75c912b0f5c414bd52e47e4f
  - claim `claim_9` [supported]: 对于焊接钢筋网和钢筋桁架，还需考虑剪切强度与焊点强度。
    evidence: 380bfaca75c912b0f5c414bd52e47e4f
  - claim `claim_10` [supported]: 设计时至少应明确钢筋的强度等级、延性等级以及直径或规格。
    evidence: d3dbb363af61cce1e53b23d1bd4b85de
- [ ] 人工确认最小充分证据集

## Q05: 请问都有那些环境暴露等级?
- status: needs_human_review
- gold_claim_status: mixed
- E⁺ (6): 10d94c8801c8c3c1f88ac2367ba2a1b2, 18133706a02589d3453125b8113303d9, 26bb5f882d77d51904527da5d93d0e58, 61fbd1b90d385b382cbecfe460928b58, f119f4c2391ac927eec632326032a705, f8db0dfdf11b81188ae1372c8e22bc5f
- pool_size: 50 strategies=['neighbor', 'vector']
- reference_answer: 按 Eurocode 2，环境暴露等级可分为：X0（无腐蚀或侵蚀风险）；XC（碳化引起的钢筋腐蚀，XC1～XC4）；XD（非海水氯化物引起的钢筋腐蚀，XD1～XD3）；XS（海水氯化物引起的钢筋腐蚀，XS1～XS3）；XF（冻融作用引起的混凝土损伤）；XA（化学侵蚀，XA1～XA3）。候选池能够确认 XF 为冻融暴露类别，但未完整展示其全部细分类别。
  - claim `claim_1` [supported]: X0表示无腐蚀或侵蚀风险的暴露等级。
    evidence: 26bb5f882d77d51904527da5d93d0e58
  - claim `claim_2` [supported]: XC为碳化引起的钢筋腐蚀暴露类别，包括XC1、XC2、XC3和XC4。
    evidence: 18133706a02589d3453125b8113303d9, 10d94c8801c8c3c1f88ac2367ba2a1b2
  - claim `claim_3` [supported]: XD为非海水来源氯化物引起的钢筋腐蚀暴露类别，包括XD1、XD2和XD3。
    evidence: 61fbd1b90d385b382cbecfe460928b58, f8db0dfdf11b81188ae1372c8e22bc5f
  - claim `claim_4` [supported]: XS为海水氯化物引起的钢筋腐蚀暴露类别，包括XS1、XS2和XS3。
    evidence: 61fbd1b90d385b382cbecfe460928b58, f8db0dfdf11b81188ae1372c8e22bc5f
  - claim `claim_5` [supported]: XF为冻融作用引起的混凝土损伤暴露类别。
    evidence: 61fbd1b90d385b382cbecfe460928b58
  - claim `claim_6` [corpus_gap]: XF类别的完整细分等级列表。
    evidence: —
  - claim `claim_7` [supported]: XA为化学侵蚀暴露类别，包括XA1、XA2和XA3。
    evidence: 61fbd1b90d385b382cbecfe460928b58, f119f4c2391ac927eec632326032a705
- [ ] 人工确认最小充分证据集

## Q06: 保护层都与什么因素相关，该怎么计算?
- status: needs_human_review
- gold_claim_status: mixed
- E⁺ (3): 5bd91554dc3a7df432e14ec8917dcd6a, 9121ae0a795a0451720935dc8c4b493c, ac60d1094175c641bcd9531b0cb82f93
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 候选池中的“保护层”可理解为受保护钢构件的防火保护层。其热响应主要与保护材料导热系数 λ_p、保护层厚度 d_p、保护材料体积热容参数 c_pρ_p、钢材体积热容参数 c_aρ_a、受火周长与钢材体积之比 A_p/V、燃气与钢材温度差、燃气温升及时间步长 Δt 有关。先计算保护层热容影响参数：φ=(c_p d_p ρ_p)/(c_a ρ_a)·(A_p/V)。随后可按增量式计算钢材温升：Δθ_a,t=[(λ_p A_p/V)/(d_p c_aρ_a)]·[(θ_g,t−θ_a,t)/(1+φ/3)]·Δt−(e^(φ/10)−1)·Δθ_g,t。候选池未提供这些符号的完整定义、单位要求、适用边
  - claim `claim_1` [supported]: 受保护钢构件的温升计算与保护材料导热系数 λ_p、保护层厚度 d_p、截面因子 A_p/V、钢材比热 c_a、钢材密度 ρ_a、燃气与钢材温度差及时间步长 Δt 有关。
    evidence: 9121ae0a795a0451720935dc8c4b493c
  - claim `claim_2` [supported]: 保护层热容影响参数可按 φ=(c_p d_pρ_p)/(c_aρ_a)·(A_p/V) 计算。
    evidence: ac60d1094175c641bcd9531b0cb82f93
  - claim `claim_3` [supported]: 考虑保护层热容影响时，钢材温升可按 Δθ_a,t=[(λ_pA_p/V)/(d_pc_aρ_a)]·[(θ_g,t−θ_a,t)/(1+φ/3)]·Δt−(e^(φ/10)−1)Δθ_g,t 计算。
    evidence: 9121ae0a795a0451720935dc8c4b493c
  - claim `claim_4` [supported]: 保护层传热系数的组合项与 (A_p/V)(λ_p/d_p) 及热容修正项有关。
    evidence: 5bd91554dc3a7df432e14ec8917dcd6a
  - claim `claim_5` [corpus_gap]: 候选池足以给出由目标耐火时间或目标钢温反算保护层厚度 d_p 的完整设计流程。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q07: 结构分析的目的是什么?
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (4): 20d0a12f8a24e4b9ed88501eadae6c9f, 805e3ab30f6fc54691c197bc66d6b12b, afa986f785f04c22e70947ae7c68db69, f21de74919a1c486f9f1972893f749be
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 结构分析的目的是确定整个结构或其某一部分中的内力和弯矩分布，或者确定应力、应变及位移的分布，从而为结构验算提供作用效应。
  - claim `claim_1` [supported]: 结构分析用于确定整个结构或其某一部分中的内力和弯矩分布。
    evidence: 20d0a12f8a24e4b9ed88501eadae6c9f, f21de74919a1c486f9f1972893f749be, afa986f785f04c22e70947ae7c68db69
  - claim `claim_2` [supported]: 结构分析也可用于确定整个结构或其某一部分中的应力、应变和位移分布。
    evidence: 805e3ab30f6fc54691c197bc66d6b12b, 20d0a12f8a24e4b9ed88501eadae6c9f, f21de74919a1c486f9f1972893f749be
  - claim `claim_3` [supported]: 结构分析所得结果可作为后续结构或截面验算的作用效应。
    evidence: 20d0a12f8a24e4b9ed88501eadae6c9f, f21de74919a1c486f9f1972893f749be
- [ ] 人工确认最小充分证据集

## Q08 `[DISPUTED]`: 在哪些部位当线性应变分布的假设不成立时，可能需要进行局部分析?
- status: needs_human_review_disputed
- gold_claim_status: supported
- E⁺ (1): 20d0a12f8a24e4b9ed88501eadae6c9f
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 当线性应变分布假设不成立时，可能需要在以下部位进行局部分析：支座附近、集中荷载作用处、梁柱交汇处、锚固区以及截面变化处。
  - claim `claim_1` [supported]: 支座附近可能需要进行局部分析。
    evidence: 20d0a12f8a24e4b9ed88501eadae6c9f
  - claim `claim_2` [supported]: 集中荷载作用处可能需要进行局部分析。
    evidence: 20d0a12f8a24e4b9ed88501eadae6c9f
  - claim `claim_3` [supported]: 梁柱交汇处可能需要进行局部分析。
    evidence: 20d0a12f8a24e4b9ed88501eadae6c9f
  - claim `claim_4` [supported]: 锚固区可能需要进行局部分析。
    evidence: 20d0a12f8a24e4b9ed88501eadae6c9f
  - claim `claim_5` [supported]: 截面变化处可能需要进行局部分析。
    evidence: 20d0a12f8a24e4b9ed88501eadae6c9f
  - **dispute** `claim_1`: evidence 是一段关于结构分析目的和'必要时需进行局部分析'的通用性陈述，并未提及'支座附近'这一具体部位，也未提及'线性应变分布假设不成立'这一前提条件。evidence 过于笼统，不能真正支持此 claim。
  - **dispute** `claim_2`: evidence 同样是通用性陈述，未提及'集中荷载作用处'，也未涉及线性应变分布假设的讨论。evidence 无法具体支持此 claim。
  - **dispute** `claim_3`: evidence 未提及'梁柱交汇处'，也没有讨论线性应变分布假设失效的场景。通用性陈述不足以支撑此具体部位 claim。
  - **dispute** `claim_4`: evidence 未提及'锚固区'，也没有涉及线性应变分布假设。evidence 仅泛泛地说'Additional local analysis shall be carried out where necessary'，不构成对锚固区的具体支持。
  - **dispute** `claim_5`: evidence 未提及'截面变化处'，也没有讨论线性应变分布假设不成立的条件。通用性陈述无法支撑此具体部位 claim。
- [ ] 人工确认最小充分证据集

## Q09: 根据性质和功能，结构构件包括哪些类型?
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (1): a59daacabce9639899320cf648bb3362
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 根据构件的性质和功能，结构构件可分为梁、柱、楼板（slabs）、墙、板（plates）、拱、壳等类型。
  - claim `claim_1` [supported]: 按性质和功能，结构构件包括梁。
    evidence: a59daacabce9639899320cf648bb3362
  - claim `claim_2` [supported]: 按性质和功能，结构构件包括柱。
    evidence: a59daacabce9639899320cf648bb3362
  - claim `claim_3` [supported]: 按性质和功能，结构构件包括楼板（slabs）。
    evidence: a59daacabce9639899320cf648bb3362
  - claim `claim_4` [supported]: 按性质和功能，结构构件包括墙。
    evidence: a59daacabce9639899320cf648bb3362
  - claim `claim_5` [supported]: 按性质和功能，结构构件包括板（plates）。
    evidence: a59daacabce9639899320cf648bb3362
  - claim `claim_6` [supported]: 按性质和功能，结构构件包括拱。
    evidence: a59daacabce9639899320cf648bb3362
  - claim `claim_7` [supported]: 按性质和功能，结构构件包括壳。
    evidence: a59daacabce9639899320cf648bb3362
- [ ] 人工确认最小充分证据集

## Q10: 什么是单向板?
- status: needs_human_review
- gold_claim_status: corpus_gap
- E⁺ (0): (none)
- pool_size: 50 strategies=['neighbor', 'vector']
- reference_answer: 候选池中没有给出“单向板”的定义，因此无法仅依据池内证据作出规范性回答。池内仅涉及“双向板”的案例及其在 X、Y 两个方向配置所需钢筋，不能据此充分定义单向板。
  - claim `claim_1` [corpus_gap]: 单向板的规范性定义可由候选池确定。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q11: 欧标的截面计算的基本假设前提是什么？
- status: needs_human_review
- gold_claim_status: mixed
- E⁺ (5): 536caff936d6c701a08a7434f69d388e, 9279616a9cc8c2c36f8ba17fd7ce5b75, b54e3e005a8546b269814d15a66e2394, c326dd1b2f029fdce3c0bf8bc990ce27, d76063662433b60cb2be97f209d847f1
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 候选池未提供欧标“截面计算基本假设”的具体条文，因此无法据此完整列出诸如应变分布、材料本构或局部屈曲处理等截面分析假设。池内只能确认其一般设计前提：采用极限状态和分项系数法，以作用、材料性能及几何数据为基本变量；对所有相关设计状况，使用这些变量的设计值进行验算，并满足作用效应设计值不超过相应抗力设计值，即 Ed≤Rd。对钢结构，承载能力极限状态的内部失效验算包括截面抗力。
  - claim `claim_1` [supported]: 欧标设计以极限状态概念和分项系数法为基本框架。
    evidence: c326dd1b2f029fdce3c0bf8bc990ce27, b54e3e005a8546b269814d15a66e2394
  - claim `claim_2` [supported]: 极限状态设计的基本变量包括作用、材料性能以及结构、构件和连接的几何数据。
    evidence: 536caff936d6c701a08a7434f69d388e, c326dd1b2f029fdce3c0bf8bc990ce27
  - claim `claim_3` [supported]: 对所有相关设计状况，应使用基本变量的设计值进行验算，确保不超过相关极限状态。
    evidence: 536caff936d6c701a08a7434f69d388e, c326dd1b2f029fdce3c0bf8bc990ce27
  - claim `claim_4` [supported]: 承载能力极限状态的一般验算条件为作用效应设计值 Ed 不大于相应抗力设计值 Rd。
    evidence: 9279616a9cc8c2c36f8ba17fd7ce5b75, d76063662433b60cb2be97f209d847f1
  - claim `claim_5` [supported]: 钢结构承载能力极限状态中的内部失效验算包括截面抗力。
    evidence: 9279616a9cc8c2c36f8ba17fd7ce5b75
  - claim `claim_6` [corpus_gap]: 截面计算所采用的具体应变分布、材料本构关系及局部屈曲处理假设可由候选池确定。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q12: 混凝土受压区应变-应力分布假设是什么？
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (3): 421c7e98dbf150af58106bd6118911db, 6c3d1b43eb874dd2ed4fd8c4d2b16d6a, 8cdc75ff75ec632f1739eb476037bb9d
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 在截面承载力计算中，假定平截面保持平面，因此混凝土应变沿截面高度呈线性分布；受压区混凝土应力按规范设计应力分布确定，可采用抛物线—矩形分布：上升段按 σcd = fcd[1-(1-εc/εc2)^2]，随后取恒定值 fcd。
  - claim `claim_1` [supported]: 截面在受力后仍保持平面，因此混凝土应变沿截面高度呈线性分布。
    evidence: 421c7e98dbf150af58106bd6118911db, 8cdc75ff75ec632f1739eb476037bb9d
  - claim `claim_2` [supported]: 混凝土受压应力应根据规范规定的设计应力分布确定。
    evidence: 8cdc75ff75ec632f1739eb476037bb9d, 421c7e98dbf150af58106bd6118911db
  - claim `claim_3` [supported]: 受压区可采用抛物线—矩形应力分布：上升段为 σcd = fcd[1-(1-εc/εc2)^2]，随后为恒定应力 fcd。
    evidence: 6c3d1b43eb874dd2ed4fd8c4d2b16d6a
- [ ] 人工确认最小充分证据集

## Q13: 混凝土压碎应变限值是多少？
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (1): 3d1ef865eb4c25e50fbc54e559bc8989
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 根据候选池中的 Eurocode 2 条文，混凝土压碎（极限压缩）应变限值为 εcu = 0.0035，即 3.5‰。
  - claim `claim_1` [supported]: 混凝土的极限压缩应变（压碎应变限值）εcu 为 0.0035，即 3.5‰。
    evidence: 3d1ef865eb4c25e50fbc54e559bc8989
- [ ] 人工确认最小充分证据集

## Q14: 极限受力状态下混凝土受压区高度限值为多少？
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (1): bca17be5c2ef1d155b5e6941032bfff5
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 在极限承载力状态下，混凝土受压区高度应满足：对于 C50/60 及以下强度等级，x/d 不应大于 0.45；对于 C55/67 及以上强度等级，x/d 不应大于 0.35。其中 x 为受压区高度，d 为截面有效高度。
  - claim `claim_1` [supported]: 对于 C50/60 及以下强度等级的混凝土，极限状态下受压区相对高度限值为 x/d ≤ 0.45。
    evidence: bca17be5c2ef1d155b5e6941032bfff5
  - claim `claim_2` [supported]: 对于 C55/67 及以上强度等级的混凝土，极限状态下受压区相对高度限值为 x/d ≤ 0.35。
    evidence: bca17be5c2ef1d155b5e6941032bfff5
- [ ] 人工确认最小充分证据集

## Q15: 弯矩重分布限值为多少？
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (1): bca17be5c2ef1d155b5e6941032bfff5
- pool_size: 37 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 按候选池中的 EC2 资料，弯矩重分布系数 δ（重分布后弯矩/重分布前弯矩）的限值取决于钢筋延性等级：B、C 级钢筋 δ ≥ 0.70，即弯矩最多重分布 30%；A 级钢筋 δ ≥ 0.80，即最多重分布 20%。
  - claim `claim_1` [supported]: 弯矩重分布系数 δ 是重分布后弯矩与重分布前弯矩之比。
    evidence: bca17be5c2ef1d155b5e6941032bfff5
  - claim `claim_2` [supported]: 采用 B 级或 C 级钢筋时，δ 不得小于 0.70，因此弯矩重分布幅度不得超过 30%。
    evidence: bca17be5c2ef1d155b5e6941032bfff5
  - claim `claim_3` [supported]: 采用 A 级钢筋时，δ 不得小于 0.80，因此弯矩重分布幅度不得超过 20%。
    evidence: bca17be5c2ef1d155b5e6941032bfff5
- [ ] 人工确认最小充分证据集

## Q16: fcd 如何计算
- status: needs_human_review
- gold_claim_status: mixed
- E⁺ (2): a73d09060775345e27f34608a1760cd2, c684c940c25030bcbbea2da77c563d34
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 候选池未直接给出 Eurocode 2 中 fcd 的完整定义公式。但示例 chunk 显示采用 fcd = 30/1.5 = 20 MPa，即以混凝土特征抗压强度除以材料分项系数。一般完整计算式及是否需要乘 αcc，应以适用版本的 EN 1992-1-1 和国家附录为准；该信息在候选池中缺失。
  - claim `claim_1` [supported]: 候选示例中，fck = 30 MPa、γC = 1.5 时，采用 fcd = 30/1.5 = 20 MPa。
    evidence: c684c940c25030bcbbea2da77c563d34
  - claim `claim_2` [supported]: 材料设计值的一般形式是特征值除以材料分项系数，即 fd = fk/γm。
    evidence: a73d09060775345e27f34608a1760cd2
  - claim `claim_3` [corpus_gap]: fcd 的完整 Eurocode 2 定义公式以及 αcc 的取值要求由适用规范版本和国家附录确定。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q17: 截面计算中材料分项安全系数为多少？
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (3): 0d6cab1499eb5c0cbc5d6e1dc23f7f44, c24bb1cb8c215880938b329f94f6aacc, d2c7f9bfd0575fb034d5bf7fad1c5399
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 钢结构截面承载力计算采用材料分项安全系数 γM0 = 1.0。该值是 EC3-1-1 的推荐值，具体工程仍应核对所在国家的国家附录。
  - claim `claim_1` [supported]: 钢结构截面承载力计算的材料分项安全系数为 γM0 = 1.0。
    evidence: d2c7f9bfd0575fb034d5bf7fad1c5399, 0d6cab1499eb5c0cbc5d6e1dc23f7f44, c24bb1cb8c215880938b329f94f6aacc
  - claim `claim_2` [supported]: EC3 的材料分项安全系数可能由国家附录规定，因此具体工程应核对适用的国家附录。
    evidence: c24bb1cb8c215880938b329f94f6aacc
- [ ] 人工确认最小充分证据集

## Q18: 混凝土抗压强度标准值、设计值与平均强度之间是什么关系？
- status: needs_human_review
- gold_claim_status: mixed
- E⁺ (3): 3d6b27f1ce4fe9ec4f50cbc9df94328e, 748733e05f718cab465d9e2891df7f4d, d3045e7be7d076638f789cbe1a3204b7
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 候选池只能确认：混凝土抗压强度标准值 f_ck 是强度试验结果的 5% 分位值，即预计不超过 5% 的试验结果低于该值；混凝土强度等级以 28 天特征圆柱抗压强度 f_ck（或相应立方体强度 f_ck,cube）表示。候选池未提供抗压强度设计值 f_cd 与 f_ck 的折减公式，也未提供平均抗压强度 f_cm 与 f_ck 的定量关系，因此无法仅依据池内证据完整说明三者之间的关系。
  - claim `claim_1` [supported]: 混凝土抗压强度标准值 f_ck 是抗压强度总体的 5% 分位值，即预计低于该值的试验结果不超过 5%。
    evidence: d3045e7be7d076638f789cbe1a3204b7, 3d6b27f1ce4fe9ec4f50cbc9df94328e, 748733e05f718cab465d9e2891df7f4d
  - claim `claim_2` [supported]: Eurocode 2 的混凝土强度等级以特征圆柱抗压强度 f_ck 或相应的特征立方体抗压强度 f_ck,cube 表示，且强度等级以 28 天强度为基础。
    evidence: 3d6b27f1ce4fe9ec4f50cbc9df94328e, d3045e7be7d076638f789cbe1a3204b7
  - claim `claim_3` [corpus_gap]: 混凝土抗压强度设计值 f_cd 由标准值 f_ck 经材料分项系数及相关系数折减得到。
    evidence: —
  - claim `claim_4` [corpus_gap]: 混凝土平均抗压强度 f_cm 与标准值 f_ck 之间存在规定的定量换算关系。
    evidence: —
  - claim `claim_5` [corpus_gap]: 抗压强度设计值、标准值和平均值通常满足设计值小于标准值、标准值小于平均值的大小关系。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q19: 钢筋的锚固长度与搭接长度受哪些因素影响？
- status: needs_human_review
- gold_claim_status: mixed
- E⁺ (9): 0340d139cf25bd250dccd480a262788c, 0beb00b08610fbd3ea0d802ff0d1c1ed, 47217e4fecc3b23a0cad0019bf9e04ab, 6e530799ae65349228d7623700205af7, 775ee56e5e23c9619e15e3cb52bd3b74, 917773a5a75c7c48dc012b9cd479ca83, bac05abdd06d5b7734d52908aa42e903, ef543ef647afe8b3813269ffdd3597df, f1a7a7581313b18aa703ceb8a3a799a0
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 根据候选池中的 Eurocode 2 证据，钢筋锚固长度主要受以下因素影响：钢筋受拉或受压状态、钢筋直径与设计应力、钢筋类型及黏结性能（包括浇筑形成的良好或不良黏结条件）、混凝土强度、锚固形式（直筋、弯折、弯钩或环形）、混凝土保护层和钢筋净间距，以及横向钢筋约束、焊接横向钢筋和横向压力。候选池未提供足够的搭接长度条文或计算内容，因此无法仅依据这些证据确定搭接长度的具体影响因素。
  - claim `claim_1` [supported]: 锚固长度受钢筋处于受拉还是受压状态的影响。
    evidence: bac05abdd06d5b7734d52908aa42e903, 6e530799ae65349228d7623700205af7, 0340d139cf25bd250dccd480a262788c
  - claim `claim_2` [supported]: 锚固长度受钢筋类型、黏结性能以及浇筑形成的良好或不良黏结条件影响。
    evidence: 917773a5a75c7c48dc012b9cd479ca83, bac05abdd06d5b7734d52908aa42e903, 6e530799ae65349228d7623700205af7
  - claim `claim_3` [supported]: 锚固长度受钢筋直径、钢筋设计应力和混凝土强度影响。
    evidence: 775ee56e5e23c9619e15e3cb52bd3b74, f1a7a7581313b18aa703ceb8a3a799a0, 917773a5a75c7c48dc012b9cd479ca83
  - claim `claim_4` [supported]: 锚固长度受锚固形状影响，包括直筋、标准弯折、弯钩或环形锚固。
    evidence: bac05abdd06d5b7734d52908aa42e903, ef543ef647afe8b3813269ffdd3597df, 0beb00b08610fbd3ea0d802ff0d1c1ed
  - claim `claim_5` [supported]: 锚固长度受混凝土保护层尺寸及钢筋净间距影响。
    evidence: 0beb00b08610fbd3ea0d802ff0d1c1ed, 47217e4fecc3b23a0cad0019bf9e04ab, 775ee56e5e23c9619e15e3cb52bd3b74
  - claim `claim_6` [supported]: 横向钢筋约束、焊接横向钢筋和横向压力会影响设计锚固长度。
    evidence: 0beb00b08610fbd3ea0d802ff0d1c1ed, 47217e4fecc3b23a0cad0019bf9e04ab
  - claim `claim_7` [corpus_gap]: 搭接长度的具体影响因素可由候选池中的条文确定。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q20 `[DISPUTED]`: 什么情况下需要考虑二阶效应？
- status: needs_human_review_disputed
- gold_claim_status: supported
- E⁺ (9): 0930ba4fc82bdd12476c9412532b09a8, 0c957f1a152c5b95919fb3f29416e25e, 107f2ee9f628472272593d3ed895a559, 2e236a4f7e089fe7dcdb38b3c5c1b2bb, 38ddff7b946dcc6581fc06e1452757dd, 4bc56ca0247d150c54790ea1c522c724, 735c85e6aaf48669ace640477acf418a, 871cfdfa7691f685f6640bad444604e2, 8f00cd7aefd77726450fc11686f0e858
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 需要考虑二阶效应的基本情形是：结构变形对受力效应或结构行为产生不可忽略的影响，特别是可能显著影响结构整体稳定性，或影响关键截面达到承载能力极限状态时。对混凝土结构，若二阶效应超过相应一阶效应的10%，通常不能忽略；对独立受压构件，当长细比 λ 达到或超过限值 λ_lim 时，应考虑二阶效应。双向弯曲时可分别在两个主平面检查，并在长细比超过限值的方向考虑。柔性支撑体系以及柱、墙、桩、拱、壳等受轴力且变形敏感的结构尤其需要检查。对钢结构，当变形显著增大作用效应或改变结构行为时应考虑；以弹性临界荷载系数判断时，α_cr≤10 通常表示需要考虑二阶效应。
  - claim `claim_1` [supported]: 当二阶效应可能显著影响结构整体稳定性或关键截面达到承载能力极限状态时，应考虑二阶效应。
    evidence: 107f2ee9f628472272593d3ed895a559
  - claim `claim_2` [supported]: 对于混凝土结构，二阶效应超过相应一阶效应的10%时，不能按规范的简化条件忽略。
    evidence: 735c85e6aaf48669ace640477acf418a, 0c957f1a152c5b95919fb3f29416e25e
  - claim `claim_3` [supported]: 对于独立受压构件，当长细比 λ 达到或超过限值 λ_lim 时，应考虑二阶效应；低于该限值时可忽略。
    evidence: 4bc56ca0247d150c54790ea1c522c724, 8f00cd7aefd77726450fc11686f0e858
  - claim `claim_4` [supported]: 双向弯曲时，可在各主弯曲平面分别检查长细比，并只在超过长细比限值的方向考虑二阶效应。
    evidence: 4bc56ca0247d150c54790ea1c522c724, 2e236a4f7e089fe7dcdb38b3c5c1b2bb
  - claim `claim_5` [supported]: 柱、墙、桩、拱、壳等受轴力且其行为明显受变形影响的构件或结构，以及采用柔性支撑体系的结构，需要重点检查二阶效应。
    evidence: 38ddff7b946dcc6581fc06e1452757dd
  - claim `claim_6` [supported]: 对于钢结构，当变形显著增大作用效应或显著改变结构行为时，应考虑二阶效应。
    evidence: 871cfdfa7691f685f6640bad444604e2
  - claim `claim_7` [supported]: 对于钢结构，以弹性临界荷载系数判断时，α_cr≤10通常需要考虑二阶效应。
    evidence: 0930ba4fc82bdd12476c9412532b09a8
  - **dispute** `claim_2`: Evidence 不支持该 claim。提供的两条 evidence（735c85e 讲术语 actions/loads 定义；0c957f1a 讲 creep 在二阶分析中的处理）均未提及 10% 阈值。claim 本身所述的 10% 规则出自 EN 1992-1-1 5.8.2(6)P，但所附 evidence 与此无关，属于 evidence-claim 不匹配。该 claim 的 evidence 不足以支撑其论断。
- [ ] 人工确认最小充分证据集

## Q21: 受弯构件正截面承载力计算的一般步骤是什么？
- status: needs_human_review
- gold_claim_status: corpus_gap
- E⁺ (0): (none)
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 候选池未包含“受弯构件正截面承载力计算一般步骤”的直接规定或完整计算流程，因此无法仅依据池内证据给出可靠的规范性答案。
  - claim `claim_1` [corpus_gap]: 受弯构件正截面承载力计算的一般步骤无法由候选池中的证据确定。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q22 `[DISPUTED]`: 后张法预应力损失如何计算
- status: needs_human_review_disputed
- gold_claim_status: mixed
- E⁺ (9): 0dea3749b7c34d2c74830f0d2006a823, 1d7c57ba4782942f71d714bdeef634e3, 298a98da66a2abe1b74c3da8c8c658dc, 3cc186a2b0abe86938475e453037cbc5, 5060ad455a1e70448979674e693473a0, 62f16f7d19c39a530680fe93618ff363, 65c7de3774988fde690cc4da65fcbcdb, e33488a32af119021123cd7a49aab4ab, f0ed75d4216411e2829ae0dc387b9177
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 按候选池中的 Eurocode 2 证据，后张法在距张拉端 x、时刻 t 的平均预应力可按“张拉端最大预应力减去即时损失和长期损失”确定，即概念上为：σp,m,t(x)=σp,max−Δσp,i(x)−Δσp,c+s+r(t)（采用力表示时同理）。即时损失应考虑孔道摩擦、锚具回缩（楔片回缩）和混凝土瞬时变形；其中摩擦损失为 Δσp,μ(x)=σp,max[1−exp(−μ(αμ+kμx))]。式中 αμ 为长度 x 内角度偏差绝对值之和，μ 为预应力筋与孔道或转向装置之间的摩擦系数，kμ 为单位长度非预期角度偏差，x 为距主动张拉端的筋束长度。混凝土瞬时变形损失应考虑各束的张拉顺序；长期损失应
  - claim `claim_1` [supported]: 后张法任意位置和时刻的平均预应力等于主动端最大预应力减去即时损失和时间相关损失。
    evidence: 1d7c57ba4782942f71d714bdeef634e3
  - claim `claim_2` [supported]: 后张法即时损失应考虑孔道摩擦、锚具回缩以及预应力传递时混凝土的瞬时变形。
    evidence: 298a98da66a2abe1b74c3da8c8c658dc, 5060ad455a1e70448979674e693473a0
  - claim `claim_3` [supported]: 摩擦损失可按 Δσp,μ(x)=σp,max[1−exp(−μ(αμ+kμx))] 计算。
    evidence: 65c7de3774988fde690cc4da65fcbcdb
  - claim `claim_4` [supported]: 摩擦公式中，αμ 是长度 x 内角度偏差绝对值之和，μ 是筋束与孔道或转向装置间的摩擦系数，kμ 是单位长度非预期角度偏差，x 是距主动张拉端的长度。
    evidence: f0ed75d4216411e2829ae0dc387b9177
  - claim `claim_5` [supported]: 摩擦参数 μ 和 kμ 宜采用后张体系技术文件中的数值。
    evidence: f0ed75d4216411e2829ae0dc387b9177, 0dea3749b7c34d2c74830f0d2006a823
  - claim `claim_6` [supported]: 混凝土瞬时变形引起的后张预应力损失应考虑各束的张拉顺序。
    evidence: 62f16f7d19c39a530680fe93618ff363, 3cc186a2b0abe86938475e453037cbc5
  - claim `claim_7` [supported]: 长期预应力损失应综合混凝土收缩、徐变和预应力钢材松弛，并可按 EN 1992-1-1:2023 式(7.35)计算。
    evidence: e33488a32af119021123cd7a49aab4ab
  - claim `claim_8` [corpus_gap]: 锚具回缩损失的具体计算公式可由当前候选池确定。
    evidence: —
  - claim `claim_9` [corpus_gap]: 混凝土瞬时变形损失的完整计算公式可由当前候选池确定。
    evidence: —
  - **dispute** `claim_8`: Claim text states '锚具回缩损失的具体计算公式可由当前候选池确定' (the formula CAN be determined from the candidate pool), but gold status=corpus_gap with evidence=(none) directly contradicts this assertion. The reference answer also confirms '当前候选池未给出锚具回缩损失的具体计算式'. The claim text is factually false — it should state the formula CANNOT be determined. The corpus_gap status itself is correct, but the claim text is self-contradictory with its own status.
  - **dispute** `claim_9`: Same issue as claim_8. Claim text states '混凝土瞬时变形损失的完整计算公式可由当前候选池确定' (the complete formula CAN be determined from the pool), but status=corpus_gap with evidence=(none) contradicts this. The reference answer confirms the pool does not fully show the concrete instantaneous deformation loss formula. The claim text should say CANNOT, not CAN. Corpus_gap status is correct but the claim text is wrong.
- [ ] 人工确认最小充分证据集

## Q23: 预应力在各类极限状态下的影响是什么
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (16): 06037f30e436ad8db4dc51439a3d59d5, 0fc5e2a9cb09f6cd39c4920dbd406bcb, 10f7d041f88e2de3075b9cdbeed05173, 1d7c57ba4782942f71d714bdeef634e3, 313e604813e2e62bf5060fbe8dd59e43, 31c6bb966bd201823c230ad786d69db9, 3da80095a78d9815acf6800e08c0a9d8, 49b45c790f1f72695987a2df3a582e15, 55ee490f61a14dee631072a8604a2f7e, 65eca110841acd91ef75049331c2aa7d, 6d9ca271662be6e59561d0be8d544132, 70f3e81616230b327c8d9a467d544605, 7601aaa5d70bd73b7ecf4dff721db055, 8e9988280ce7a184e7c780f04f250df3, 9d3c4b22a392c5742be1e3d599759bc4, a94ae3a44a81812f70a87ba583da5f10
- pool_size: 50 strategies=['neighbor', 'vector']
- reference_answer: 预应力在 Eurocode 中通常作为永久作用处理，其效应可采用两种等效方式计入：作为外部作用，或作为由预应变、预曲率形成的抗力。采用哪种方式都应保持作用效应与截面抗力计算的一致性，避免重复计入；预应力产生的弯矩和轴力应纳入相应作用组合。

在承载能力极限状态（ULS）中，预应力多数情况下是有利作用，通常采用有利预应力分项系数；但在外预应力稳定验算中，预应力增大可能不利，此时应采用不利值，局部效应验算也应按不利预应力考虑。抗弯承载力验算时，若把预应力作为外部作用，预应力筋的抗力仅计入其超过已有预应力应力的增量；若在抗力侧考虑，则可按预应力筋完整设计强度计入。还应防止预应力筋失效导致构件脆性破坏
  - claim `claim_1` [supported]: 预应力应归类为永久作用。
    evidence: 65eca110841acd91ef75049331c2aa7d, 31c6bb966bd201823c230ad786d69db9, a94ae3a44a81812f70a87ba583da5f10
  - claim `claim_2` [supported]: 预应力效应可作为外部作用，也可作为由预应变和预曲率形成的抗力考虑。
    evidence: 06037f30e436ad8db4dc51439a3d59d5, 70f3e81616230b327c8d9a467d544605, 55ee490f61a14dee631072a8604a2f7e
  - claim `claim_3` [supported]: 预应力应进入作用组合，其效应应计入施加于结构的内力矩和轴力。
    evidence: 06037f30e436ad8db4dc51439a3d59d5, 8e9988280ce7a184e7c780f04f250df3
  - claim `claim_4` [supported]: 承载能力极限状态验算中，预应力在多数情况下属于有利效应，应采用有利预应力分项系数；持久和暂时设计状况的推荐值为1.0。
    evidence: 7601aaa5d70bd73b7ecf4dff721db055, 3da80095a78d9815acf6800e08c0a9d8, 9d3c4b22a392c5742be1e3d599759bc4
  - claim `claim_5` [supported]: 外预应力稳定极限状态中，预应力增大可能产生不利影响，此时应采用不利预应力值；规范推荐的整体分析分项系数为1.3。
    evidence: 7601aaa5d70bd73b7ecf4dff721db055, 3da80095a78d9815acf6800e08c0a9d8, 9d3c4b22a392c5742be1e3d599759bc4
  - claim `claim_6` [supported]: 预应力局部效应验算应采用不利预应力分项系数。
    evidence: 7601aaa5d70bd73b7ecf4dff721db055
  - claim `claim_7` [supported]: ULS抗弯验算中，若预应力作为外部作用，预应力筋抗力应限于设计强度减去已有设计预应力应力；若预应力在抗力侧考虑，则可限于预应力筋完整设计强度。
    evidence: 10f7d041f88e2de3075b9cdbeed05173
  - claim `claim_8` [supported]: 应避免预应力筋失效导致构件发生脆性破坏。
    evidence: 06037f30e436ad8db4dc51439a3d59d5, 8e9988280ce7a184e7c780f04f250df3
  - claim `claim_9` [supported]: 正常使用极限状态中，预应力应按相应作用组合计入；裂缝控制所用轴力应考虑预应力特征值。
    evidence: 313e604813e2e62bf5060fbe8dd59e43, 0fc5e2a9cb09f6cd39c4920dbd406bcb
  - claim `claim_10` [supported]: 预应力宜用上、下特征值表示；对于ULS，在其他 Eurocode 允许时可采用单一特征值。
    evidence: 65eca110841acd91ef75049331c2aa7d, 31c6bb966bd201823c230ad786d69db9
  - claim `claim_11` [supported]: 用于ULS的有利预应力分项系数推荐值1.0也可用于疲劳验算。
    evidence: 7601aaa5d70bd73b7ecf4dff721db055, 3da80095a78d9815acf6800e08c0a9d8, 9d3c4b22a392c5742be1e3d599759bc4
  - claim `claim_12` [supported]: 各极限状态验算采用的有效预应力应考虑位置、时间、即时损失和长期损失的影响。
    evidence: 1d7c57ba4782942f71d714bdeef634e3, 49b45c790f1f72695987a2df3a582e15, 6d9ca271662be6e59561d0be8d544132
- [ ] 人工确认最小充分证据集

## Q24: 剪应力一般验证程序是怎样的
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (3): 61b700ba31eec4674d69610bf7284546, 97c1276e8df3f4324f6457c6bd6b8298, e8cf43020180dfe647efc2551ec3c1aa
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 一般剪切验证应在所有关键控制截面进行：首先检查 τEd ≤ 2τRdc,min；满足时可省略详细抗剪验算。否则，若 τEd ≤ τRd,c，则不需要按计算配置抗剪钢筋；若 τEd > τRd,c，则应按相应条款设计抗剪钢筋。即使计算表明不需要抗剪钢筋，线性构件仍可能需要按第12条配置最小抗剪钢筋；对于静定结构中有效高度 d > 500 mm 的线性构件，应配置最小抗剪钢筋。
  - claim `claim_1` [supported]: 剪切承载力应在所有关键控制截面进行验证。
    evidence: e8cf43020180dfe647efc2551ec3c1aa, 61b700ba31eec4674d69610bf7284546
  - claim `claim_2` [supported]: 当 τEd ≤ 2τRdc,min 时，可以省略详细抗剪验算。
    evidence: 61b700ba31eec4674d69610bf7284546, 97c1276e8df3f4324f6457c6bd6b8298
  - claim `claim_3` [supported]: 当 τEd ≤ τRd,c 时，不需要按计算配置抗剪钢筋。
    evidence: e8cf43020180dfe647efc2551ec3c1aa, 61b700ba31eec4674d69610bf7284546
  - claim `claim_4` [supported]: 当 τEd > τRd,c 时，应按相应条款设计抗剪钢筋。
    evidence: e8cf43020180dfe647efc2551ec3c1aa, 61b700ba31eec4674d69610bf7284546
  - claim `claim_5` [supported]: 即使计算上不需要抗剪钢筋，线性构件仍可能需要按第12条配置最小抗剪钢筋。
    evidence: e8cf43020180dfe647efc2551ec3c1aa, 61b700ba31eec4674d69610bf7284546
  - claim `claim_6` [supported]: 对于静定结构中有效高度 d > 500 mm 的线性构件，应配置最小抗剪钢筋。
    evidence: e8cf43020180dfe647efc2551ec3c1aa, 61b700ba31eec4674d69610bf7284546
- [ ] 人工确认最小充分证据集

## Q25: 单向板的设计步骤包括哪些
- status: needs_human_review
- gold_claim_status: corpus_gap
- E⁺ (0): (none)
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 候选池中没有提供“单向板设计步骤”的具体条文或算例，因此无法仅依据池内证据可靠列出其设计流程。
  - claim `claim_1` [corpus_gap]: 单向板的具体设计步骤可由候选池中的证据确定。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q26: 单向板构造配筋有什么规定
- status: needs_human_review
- gold_claim_status: corpus_gap
- E⁺ (0): (none)
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 候选池中没有提供关于单向板构造配筋的具体条文，无法据此确定其受力钢筋、分布钢筋、最小配筋率、钢筋间距、支座构造或锚固等规定。现有证据仅涉及板的弯曲设计、钢筋的一般布置与间距原则，不能作为单向板构造配筋要求的充分依据。
  - claim `claim_1` [corpus_gap]: 候选池未包含单向板构造配筋的具体规定。
    evidence: —
  - claim `claim_2` [corpus_gap]: 无法根据候选池确定单向板受力钢筋和分布钢筋的最小配筋量、间距、支座构造及锚固要求。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q27: 单向板分布筋的配置有什么规定
- status: needs_human_review
- gold_claim_status: corpus_gap
- E⁺ (0): (none)
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 候选池中没有提供单向板分布筋的配置条文，无法据此确定分布筋的布置方向、最小配筋量、最大间距等具体规定。池内相关内容仅涉及一般钢筋间距、平板柱节点配筋或楼盖横肋，不能作为该问题的直接依据。
  - claim `claim_1` [corpus_gap]: 单向板分布筋的布置方向规定。
    evidence: —
  - claim `claim_2` [corpus_gap]: 单向板分布筋的最小配筋量规定。
    evidence: —
  - claim `claim_3` [corpus_gap]: 单向板分布筋的最大间距规定。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q28: 构件在哪些情况下无需设计抗剪力钢筋
- status: needs_human_review
- gold_claim_status: corpus_gap
- E⁺ (0): (none)
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 候选池未提供足够证据，无法确定构件无需设计抗剪钢筋的具体判定条件。池内仅给出了无抗剪钢筋时的混凝土抗剪承载力表达式、局部剪应力条件以及疲劳验算说明，但没有完整说明何时可判定“不需要设计抗剪钢筋”。
  - claim `claim_1` [corpus_gap]: 构件无需设计抗剪钢筋的具体判定条件无法根据当前候选池确定。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q29: 需要设计剪力筋的构件有什么特征
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (3): 140b8d1c81683514f925b8ce8f9eeca6, 25a844d0b9a105fa6372f511d5869c47, b8e0a37d0e2bd873041e7511e3c4b571
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 需要进行剪力筋计算设计的构件，其关键判据是构件某区域的设计剪力 V_Ed 超过无剪力筋构件的设计抗剪承载力 V_Rd,c。此类构件按桁架模型进行抗剪设计，并配置与构件纵轴成 45°～90°的剪力筋；剪力筋可采用箍筋、弯起钢筋或适当锚固的钢筋笼、梯架等形式。
  - claim `claim_1` [supported]: 当构件某区域的设计剪力 V_Ed 超过无剪力筋时的设计抗剪承载力 V_Rd,c，该区域需要进行剪力筋计算设计。
    evidence: b8e0a37d0e2bd873041e7511e3c4b571
  - claim `claim_2` [supported]: 需要剪力筋的构件按桁架模型进行抗剪设计。
    evidence: 25a844d0b9a105fa6372f511d5869c47
  - claim `claim_3` [supported]: 剪力筋与构件纵轴的夹角应为 45°～90°。
    evidence: 140b8d1c81683514f925b8ce8f9eeca6
  - claim `claim_4` [supported]: 剪力筋可由箍筋、弯起钢筋，或在受压区和受拉区适当锚固的钢筋笼、梯架等组成。
    evidence: 140b8d1c81683514f925b8ce8f9eeca6
- [ ] 人工确认最小充分证据集

## Q30 `[DISPUTED]`: 结构抗扭转设计程序是怎样的
- status: needs_human_review_disputed
- gold_claim_status: mixed
- E⁺ (3): 175ba269d5e6a57a8b5ea645657f4843, 3e2dd4f9c6ad3791512d28c0e9f16cd1, 6aeee0ec607503f699a442d285f185c5
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 按候选池中的 Eurocode 2 资料，结构抗扭转设计可概括为：首先判断扭矩的性质。若结构静力平衡依赖其抗扭能力，则必须进行抗扭承载力计算；若扭转仅由变形协调产生，则主要按避免过度开裂进行设计。设计原则上应同时考虑正常使用极限状态和承载能力极限状态，但池内资料指出具体计算规则仅针对承载能力极限状态。抗扭钢筋采用变角桁架法设计，压杆倾角应与同时存在的剪力设计所采用的倾角一致；正常使用性能可通过满足构造要求来保证。对于协调扭转，应配置满足规定构造要求的箍筋和纵向钢筋。对于紧凑或闭合截面，池内还给出了最大抗扭剪应力表达式：τ_t,Rd,max = νf_cd/(cotθ + tanθ)。候选池未提
  - claim `claim_1` [supported]: 抗扭设计首先应区分静力平衡扭转和变形协调扭转。
    evidence: 3e2dd4f9c6ad3791512d28c0e9f16cd1
  - claim `claim_2` [supported]: 当结构静力平衡依赖构件的抗扭能力时，必须计算其抗扭承载力。
    evidence: 3e2dd4f9c6ad3791512d28c0e9f16cd1, 6aeee0ec607503f699a442d285f185c5
  - claim `claim_3` [supported]: 抗扭设计原则上应考虑正常使用极限状态和承载能力极限状态，但候选资料中的具体设计规则仅针对承载能力极限状态。
    evidence: 3e2dd4f9c6ad3791512d28c0e9f16cd1, 6aeee0ec607503f699a442d285f185c5
  - claim `claim_4` [supported]: 抗扭钢筋采用变角桁架法设计，压杆倾角应与同时存在的剪力设计所采用的倾角一致。
    evidence: 3e2dd4f9c6ad3791512d28c0e9f16cd1, 6aeee0ec607503f699a442d285f185c5
  - claim `claim_5` [supported]: 满足规定的构造要求时，可认为抗扭设计的正常使用性能要求得到满足。
    evidence: 3e2dd4f9c6ad3791512d28c0e9f16cd1, 6aeee0ec607503f699a442d285f185c5
  - claim `claim_6` [supported]: 当扭转仅由变形协调产生时，应按避免过度开裂进行设计，并使箍筋和纵向钢筋满足规定的构造要求。
    evidence: 3e2dd4f9c6ad3791512d28c0e9f16cd1, 6aeee0ec607503f699a442d285f185c5
  - claim `claim_7` [supported]: 紧凑或闭合截面的最大抗扭剪应力可按 τ_t,Rd,max = νf_cd/(cotθ + tanθ) 计算。
    evidence: 175ba269d5e6a57a8b5ea645657f4843
  - claim `claim_8` [corpus_gap]: 候选池提供了从扭矩效应计算、截面几何参数确定、配筋计算到组合验算的完整逐步抗扭设计程序。
    evidence: —
  - **dispute** `claim_1`: claim 文本本身符合 EN 1992-1-1 的逻辑（区分平衡扭转与协调扭转），但所引 evidence 仅为 3e2dd4f9（Table 1.22 钢梁侧扭屈曲曲线表），与混凝土抗扭设计完全无关，不构成对该 claim 的有效支撑。正确的 evidence 应为 6aeee0ec（EN 1992-1-1 torsional resistance 段落），该段虽未完整展开协调扭转定义，但已隐含区分。evidence 标注有误。
- [ ] 人工确认最小充分证据集

## Q31: 其他通用问题：
- status: needs_human_review
- gold_claim_status: corpus_gap
- E⁺ (0): (none)
- pool_size: 50 strategies=['neighbor', 'vector']
- reference_answer: 问题仅写明“其他通用问题”，未提供具体的 Eurocode 技术问题、适用场景或待核实事项，因此无法依据候选池给出明确的规范结论。请补充具体问题。
  - claim `claim_1` [corpus_gap]: 现有候选池无法支持针对某一具体 Eurocode 技术事项的结论，因为问题未明确所问内容。
    evidence: —
- [ ] 人工确认最小充分证据集
