# Gold 最小充分证据集人工复核 (20260712_095443)

范围：**全部题目**。任务 = 确认每题 E⁺ 是否为支持 claims 的最小充分集。
模型分歧题额外标 `[DISPUTED]`。

题数：3

## Q01: 请给出混凝土结构设计中相关作用荷载和材料的分项系数。
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (8): 35d57a7076d7fb05618f174c1dbfd86e, 35eb4a9edcf9e2ca53e5fe6a931e26ba, 54db97f8efccf4a8a44d81fbca24f2f8, 9688579d101aa7f2ccf09f7a2d24de51, b35b164167f2628cfed20b488ad96390, c020cd1200b8c315f905ae57a13974c4, c5d748c134cc7b672baf155137cf9c6a, e3fc1531ef96bcfc60bd9ebf677808e9
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 根据候选池内证据，混凝土结构设计可采用以下分项系数：在承载能力极限状态的典型基本组合中，永久作用分项系数 γG=1.35，可变作用分项系数 γQ=1.50；混凝土材料分项系数 γc=1.50，钢筋材料分项系数 γs=1.15。正常使用极限状态计算中，材料性能的分项系数通常取 1.0。具体工程的作用组合及取值仍应结合适用的国家附录确定。
  - claim `claim_1` [supported]: 承载能力极限状态的典型基本组合中，永久作用分项系数 γG 可取 1.35。
    evidence: 54db97f8efccf4a8a44d81fbca24f2f8, 9688579d101aa7f2ccf09f7a2d24de51
  - claim `claim_2` [supported]: 承载能力极限状态的典型基本组合中，可变作用分项系数 γQ 可取 1.50。
    evidence: 54db97f8efccf4a8a44d81fbca24f2f8, 9688579d101aa7f2ccf09f7a2d24de51
  - claim `claim_3` [supported]: 混凝土材料分项系数 γc 可取 1.50。
    evidence: 35d57a7076d7fb05618f174c1dbfd86e, b35b164167f2628cfed20b488ad96390, c020cd1200b8c315f905ae57a13974c4
  - claim `claim_4` [supported]: 钢筋材料分项系数 γs 可取 1.15。
    evidence: 35d57a7076d7fb05618f174c1dbfd86e, b35b164167f2628cfed20b488ad96390, c020cd1200b8c315f905ae57a13974c4
  - claim `claim_5` [supported]: 正常使用极限状态计算中，材料性能的分项系数通常取 1.0。
    evidence: e3fc1531ef96bcfc60bd9ebf677808e9
  - claim `claim_6` [supported]: 具体工程的作用组合及分项系数取值应结合适用的国家附录确定。
    evidence: 35eb4a9edcf9e2ca53e5fe6a931e26ba, c5d748c134cc7b672baf155137cf9c6a
- [ ] 人工确认最小充分证据集

## Q02: 请给出混凝土材料的强度与变形的相关定义、相互关系及如何计算。
- status: needs_human_review
- gold_claim_status: mixed
- E⁺ (4): 344157c7debd304b2859e15bfcfddb29, 35d57a7076d7fb05618f174c1dbfd86e, b1c56ada9b50bee627f7b881b5ff9d5e, b4d264f362ae3541f62c4717c1c5285d
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 候选池只能支持对混凝土强度与弹性变形作部分说明，无法完整给出 Eurocode 2 中全部定义和计算式。

强度方面，混凝土按圆柱体抗压强度特征值 fck 划分强度等级；表 3.1列出了 fck=12～90 MPa及相应立方体强度值。示例中，C25/30混凝土取 fck=25 N/mm²，并按 fctm=0.30·fck^(2/3) 计算平均轴心抗拉强度，得到约2.56 N/mm²。

变形方面，平均弹性模量 Ecm 定义为混凝土应力从0至0.4fcm之间的割线模量。混凝土弹性变形及Ecm受其组成、尤其是骨料性质影响：以石英岩骨料的表值为基准，石灰岩和砂岩骨料的Ecm分别降低10%和30%，玄
  - claim `claim_1` [supported]: 混凝土强度等级以圆柱体抗压强度特征值fck表示，表3.1列出了fck为12～90 MPa的强度等级及相应立方体强度值。
    evidence: b4d264f362ae3541f62c4717c1c5285d
  - claim `claim_2` [supported]: 对于示例中的C25/30混凝土，fck=25 N/mm²，平均轴心抗拉强度按fctm=0.30·fck^(2/3)计算，结果约为2.56 N/mm²。
    evidence: 35d57a7076d7fb05618f174c1dbfd86e
  - claim `claim_3` [supported]: 混凝土平均弹性模量Ecm是应力从0至0.4fcm范围内的割线模量。
    evidence: b1c56ada9b50bee627f7b881b5ff9d5e
  - claim `claim_4` [supported]: 混凝土的弹性变形和弹性模量受材料组成、尤其是骨料性质影响。
    evidence: b1c56ada9b50bee627f7b881b5ff9d5e
  - claim `claim_5` [supported]: 相对于石英岩骨料混凝土的表列Ecm，石灰岩和砂岩骨料应分别降低10%和30%，玄武岩骨料应提高20%。
    evidence: b1c56ada9b50bee627f7b881b5ff9d5e
  - claim `claim_6` [supported]: 混凝土弹性模量随龄期的变化可根据龄期t时的平均抗压强度fcm(t)进行估算。
    evidence: b1c56ada9b50bee627f7b881b5ff9d5e
  - claim `claim_7` [supported]: 构件刚度计算通常可采用混凝土平均弹性模量和未开裂毛截面惯性矩；计算开裂、收缩或沉降相关变形时，应采用开裂截面的折减刚度。
    evidence: 344157c7debd304b2859e15bfcfddb29
  - claim `claim_8` [corpus_gap]: 候选池可完整确定fcm、fctk、fcd等混凝土强度指标的定义及相互换算公式。
    evidence: —
  - claim `claim_9` [corpus_gap]: 候选池可完整确定Ecm由混凝土强度计算以及Ecm随龄期变化的具体公式。
    evidence: —
  - claim `claim_10` [corpus_gap]: 候选池可完整给出混凝土单轴受压应力—应变关系、峰值应变和极限应变的定义及计算。
    evidence: —
  - claim `claim_11` [corpus_gap]: 候选池可完整给出混凝土徐变和收缩变形的定义及计算方法。
    evidence: —
- [ ] 人工确认最小充分证据集

## Q03: 有哪些因素会对混凝土的徐变与收缩产生影响?
- status: needs_human_review
- gold_claim_status: supported
- E⁺ (4): 38aa169478df9a081effd396beb31679, ad4cdde0af53b6447694577452b5f413, bb3c322a3a0937199dce5ba0aedf29be, eb8cc418a1026d54d4c8fcd40f3bb009
- pool_size: 50 strategies=['bm25', 'neighbor', 'vector']
- reference_answer: 根据候选池中的 Eurocode 2 条文，混凝土徐变与收缩主要受环境湿度、构件尺寸以及混凝土组成影响。徐变还受首次加载时混凝土的龄期（成熟度）、荷载持续时间和荷载大小影响；当加载时压应力较高时，还需考虑徐变的非线性。对于收缩，干燥收缩还受构件尺寸、形状和温度影响；基本收缩则与水胶比及混凝土强度有关。
  - claim `claim_1` [supported]: 环境湿度会影响混凝土的徐变与收缩。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009, 38aa169478df9a081effd396beb31679, bb3c322a3a0937199dce5ba0aedf29be
  - claim `claim_2` [supported]: 构件尺寸会影响混凝土的徐变与收缩。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009, 38aa169478df9a081effd396beb31679
  - claim `claim_3` [supported]: 混凝土组成会影响混凝土的徐变与收缩。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009, 38aa169478df9a081effd396beb31679
  - claim `claim_4` [supported]: 首次施加荷载时混凝土的龄期或成熟度会影响徐变。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009, 38aa169478df9a081effd396beb31679
  - claim `claim_5` [supported]: 荷载的持续时间会影响混凝土徐变。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009
  - claim `claim_6` [supported]: 荷载或压应力的大小会影响混凝土徐变，高压应力下还需考虑徐变的非线性。
    evidence: eb8cc418a1026d54d4c8fcd40f3bb009, 38aa169478df9a081effd396beb31679
  - claim `claim_7` [supported]: 干燥收缩受构件尺寸、形状和温度影响。
    evidence: bb3c322a3a0937199dce5ba0aedf29be, ad4cdde0af53b6447694577452b5f413
  - claim `claim_8` [supported]: 基本收缩与水灰比有关，并因而与混凝土强度有关。
    evidence: bb3c322a3a0937199dce5ba0aedf29be
- [ ] 人工确认最小充分证据集
