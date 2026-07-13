# Gold 最小充分证据集人工复核 (20260713_172844)

范围：全部题目。只有人工确认后该题才可进入正式 CRec。

## Q01: 请给出混凝土结构设计中相关作用荷载和材料的分项系数。
- status: review_not_converged
- reference_answer: 按所引 EN 1990:2002 与 EN 1992-1-1:2004 的推荐值：对持久/短暂设计状况的建筑静力平衡（EQU，Set A）验算，作用分项系数为不利永久作用 1.10、有利永久作用 0.90、不利可变作用 1.50（有利时为 0）；国家附录可设定这些 γ 值。偶然及地震设计状况的承载能力极限状态作用分项系数宜取 1.0。正常使用极限状态的作用分项系数也宜取 1.0，除非 EN 1991 至 EN 1999 另有规定。

承载能力极限状态材料推荐分项系数为：持久/短暂状况混凝土 1.5、普通钢筋 1.15、预应力钢 1.15；偶然状况分别为 1.2、1.0、1.0。正常使用极限状态材料系数应按 EN 1992 的具体条文取值；火灾设计不适用表 2.1N 的材料推荐值，应参照 EN 1992-1-2。
- `claim_1` [supported]: 对持久和短暂设计状况，EN 1990:2002 建筑静力平衡（EQU，Set A）的推荐作用分项系数为：不利永久作用 γG,j,sup=1.10、有利永久作用 γG,j,inf=0.90；不利主导及伴随可变作用 γQ=1.50，有利时为 0。国家附录可设定这些 γ 值。
  evidence: evidence_1
- `claim_2` [supported]: EN 1990:2002 规定：偶然和地震设计状况下，承载能力极限状态的作用分项系数宜取 1.0。
  evidence: evidence_2
- `claim_3` [supported]: EN 1990:2002 规定：正常使用极限状态的作用分项系数宜取 1.0；若 EN 1991 至 EN 1999 另有规定，则按其规定。
  evidence: evidence_3
- `claim_4` [supported]: EN 1992-1-1:2004 对承载能力极限状态材料的推荐分项系数为：持久及短暂设计状况，混凝土 γc=1.5、普通钢筋 γs=1.15、预应力钢 γps=1.15；偶然设计状况分别为 1.2、1.0、1.0。
  evidence: evidence_4
- `claim_5` [supported]: 正常使用极限状态的材料分项系数应按 EN 1992-1-1:2004 的具体条文取值；表 2.1N 的材料推荐值不适用于火灾设计，火灾设计应参照 EN 1992-1-2。
  evidence: evidence_5, evidence_6
  - `evidence_1` EN1990_2002/EN1990_2002.md / A1.3 Ultimate limit states: Table A1.2(A) - Design values of actions (EQU) (Set A)
<table><tr><td rowspan="2">Persistent and transient design situations</td><td colspan="2">Permanent actions</td><td rowspan="2">Leading variable action (*)</td><td colspan="2">Accompanying variable actions</td></tr><tr><td>Unfavourable</td><td>Favourable</td><td>Main (if any)</td><td>Others</td></tr><tr><td>(Eq. 6.10)</td><td> $\gamma _ { \mathrm { G j , s u p } } G _ { \mathrm { k j , s u p } }$ </td><td> $\gamma _ { \mathrm { G j , i n f } } G _ { \mathrm { k j , i n f } }$ </td><td> $\gamma _ { \mathrm { Q , 1 } } \mathrm { Q } _ { \mathrm { k , 1 } }$ </td><td></td><td> $\gamma _ { \mathrm { Q , i } } \psi _ { 0 , \mathrm { i } } Q _ { \mathrm { k , i } }$ </td></tr><tr><td colspan="6">(*) Variable actions are those considered in Table A1.1 NOTE 1 The γ values may be set by the National annex. The recommended set of values for γ are :  $\gamma _ { \mathrm { G j , s u p } } = 1 , 1 0$   $\gamma _ { \mathrm { G j , i n f } } = 0 { , } 9 0$   $\gamma _ { \mathrm { Q , 1 } } = 1 \mathrm { , } 5 0$  where unfavourable (0 where favourable)  $\gamma _ { \mathrm { Q , i } } = 1 , 5 0$  where unfavourable (0 where favourable)
  - `evidence_2` EN1990_2002/EN1990_2002.md / A1.3.2 Design values of actions in the accidental and seismic design situations: (1) The partial factors for actions for the ultimate limit states in the accidental and seismic design situations (expressions 6.11a to 6.12b) should be 1,0. - values are given in Table A1.1.
  - `evidence_3` EN1990_2002/EN1990_2002.md / A1.4.1 Partial factors for actions: (1) For serviceability limit states the partial factors for actions should be taken as 1,0 except if differently specified in EN 1991 to EN 1999.
  - `evidence_4` EN1992-1-1_2004/EN1992-1-1_2004.md / 2.4.2.4 Partial factors for materials: Table 2.1N: Partial factors for materials for ultimate limit states
<table><tr><td rowspan=1 colspan=1>Design situations</td><td rowspan=1 colspan=1>Yc for concrete</td><td rowspan=1 colspan=1>Ys for reinforcing steel</td><td rowspan=1 colspan=1>Yys for prestressing steel</td></tr><tr><td rowspan=1 colspan=1>Persistent&amp;Transient</td><td rowspan=1 colspan=1>1.5</td><td rowspan=1 colspan=1>1,15</td><td rowspan=1 colspan=1>1,15</td></tr><tr><td rowspan=1 colspan=1>Accidental</td><td rowspan=1 colspan=1>1,2</td><td rowspan=1 colspan=1>1,0</td><td rowspan=1 colspan=1>1.0</td></tr></table>
  - `evidence_5` EN1992-1-1_2004/EN1992-1-1_2004.md / 2.4.2.4 Partial factors for materials: (2) The values for partial factors for materials for serviceability limit state verification should be taken as those given in the particular clauses of this Eurocode.
  - `evidence_6` EN1992-1-1_2004/EN1992-1-1_2004.md / 2.4.2.4 Partial factors for materials: Note: The values of C and $\gamma _ { \mathsf { S } }$ for use in a Country may be found in its National Annex. The recommended values for ‘persistent & transient’ and ‘accidental, design situations are given in Table 2.1N. These are not valid for fire design for which reference should be made to EN 1992-1-2.
- [ ] 人工确认最小充分证据集

## Q02: 请给出混凝土材料的强度与变形的相关定义、相互关系及如何计算。
- status: review_not_converged
- reference_answer: 混凝土抗压强度以特征（5%）圆柱抗压强度 fck 对应的强度等级表示；参考龄期一般为28天，项目规定时可取28至91天。由 fck 可得平均抗压强度 fcm=fck+8 MPa，并按强度区间计算平均抗拉强度 fctm。弹性模量可近似采用 Ecm=kE·fcm^(1/3)，它是从零应力至0.4fcm的割线模量。恒定压应力下的徐变应变为 εcc(t,t0)=φ(t,t0)·σc/Ec,28，且 φ=φbc+φdc；总收缩或膨胀应变为 εcs=εcbs+εcds，其中包括基本收缩和水分损失导致的附加干燥收缩。矩形截面长期挠度可基于长期性质 Ec,eff 作线弹性分析，按 δ=kI[δloads+ksδεcs] 计入荷载和收缩；部分开裂构件则以 αδ=(1-ζ)αI+ζαII 在未开裂与全开裂状态之间确定变形参数。
- `c1` [supported]: 混凝土抗压强度以与特征（5%）圆柱抗压强度 fck 相关的强度等级表示；参考龄期一般取28天，项目规定时可取28至91天。
  evidence: e1
- `c2` [supported]: 平均圆柱抗压强度为 fcm=fck+8 MPa；平均抗拉强度 fctm 在 fck≤50 MPa 时为 0.3fck^(2/3)，在 fck>50 MPa 时为 1.1fck^(1/3)。
  evidence: e2
- `c3` [supported]: 可按 Ecm=kE·fcm^(1/3) 估算弹性模量；该量对应 σc=0 至 σc=0.4fcm 之间的割线模量。
  evidence: e3
- `c4` [supported]: 恒定压应力下的徐变应变为 εcc(t,t0)=φ(t,t0)·σc/Ec,28；总平均徐变系数为 φ(t,t0)=φbc(t,t0)+φdc(t,t0)。
  evidence: e4, e5
- `c5` [supported]: 总平均收缩或膨胀应变为 εcs(t,ts)=εcbs(t)+εcds(t-ts)：前者为无水分损失时也会发生的基本收缩，后者为发生水分损失时的附加干燥收缩。
  evidence: e6
- `c6` [supported]: 矩形截面的长期挠度可用采用长期性质 Ec,eff 的线弹性分析，并按 δ=kI[δloads+ksδεcs] 计算；预期会开裂但未完全开裂的构件，变形参数按 αδ=(1-ζ)αI+ζαII 在未开裂与全开裂状态之间取值。
  evidence: e7, e8
  - `e1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 5.1.3 Strength: (1) The compressive strength of concrete shall be denoted by concrete strength classes which relate to the characteristic (5 %) cylinder strength $f _ { \mathrm { c k } }$ of the concrete in accordance with EN 206, determined at an age $t _ { \mathrm { r e f } } .$
  - `e2` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 5.1.3 Strength: <tr><td rowspan=1 colspan=1>fcm</td><td rowspan=1 colspan=1>20</td><td rowspan=1 colspan=1>24</td><td rowspan=1 colspan=1>28</td><td rowspan=1 colspan=1>33</td><td rowspan=1 colspan=1>38</td><td rowspan=1 colspan=1>43</td><td rowspan=1 colspan=1>48</td><td rowspan=1 colspan=1>53</td><td rowspan=1 colspan=1>58</td><td rowspan=1 colspan=1>63</td><td rowspan=1 colspan=1>68</td><td rowspan=1 colspan=1>78</td><td rowspan=1 colspan=1>88</td><td rowspan=1 colspan=1>98</td><td rowspan=1 colspan=1>108</td><td rowspan=1 colspan=1>fcm = fck + 8 MPa</td></tr><tr><td rowspan=1 colspan=1>fctm</td><td rowspan=1 colspan=1>1,6</td><td rowspan=1 colspan=1>1,9</td><td rowspan=1 colspan=1>2,2</td><td rowspan=1 colspan=1>2,6</td><td rowspan=1 colspan=1>2,9</td><td rowspan=1 colspan=1>3,2</td><td rowspan=1 colspan=1>3,5</td><td rowspan=1 colspan=1>3,8</td><td rowspan=1 colspan=1>4,1</td><td rowspan=1 colspan=1>4,2</td><td rowspan=1 colspan=1>4,3</td><td rowspan=1 colspan=1>4,5</td><td rowspan=1 colspan=1>4,7</td><td rowspan=1 colspan=1>4,9</td><td rowspan=1 colspan=1>5,1</td><td rowspan=1 colspan=1>fctm = 0,3fck2/3(fck ≤ 50 MPa)fctm = 1,1fck1/3(fck &gt; 50 MPa)</td></tr>
  - `e3` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 5.1.4 Elastic deformation: (2) Approximate indicative values for the modulus of elasticity $E _ { \mathrm { c m } }$ may be taken as:

$$
E _ { \mathrm { c m } } = k _ { \mathrm { E } } \cdot f _ { \mathrm { c m } } 1 / 3\tag{5.1}
$$

For concrete with quartzite aggregates $k _ { \mathrm { E } } = 9 ~ 5 0 0$ may be assumed. For other types of aggregates $k _ { \mathrm { E } }$ can vary between 5 000 and 13 000.

NOTE 1 The National Annex can specify values <sup>k</sup>E to be used in the country.

NOTE 2 <sup>E</sup> corresponds to the secant modulus between $\sigma _ { \mathrm { c } } = 0$ and $\sigma _ { \mathrm { c } } = 0 { , } 4 f _ { \mathrm { c m } }$ .
  - `e4` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 5.1.5 Creep and shrinkage: (1) The creep deformation of concrete $\varepsilon _ { \mathrm { c c } } ( t , t _ { 0 } )$ at time <sup>t</sup> for a constant compressive stress $\sigma _ { \mathrm { c } }$ applied at the concrete age $t _ { 0 } ,$ shall be given by:

$$
\varepsilon _ { \mathrm { c c } } ( t , t _ { 0 } ) = \varphi ( t , t _ { 0 } ) \cdot ( \sigma _ { \mathrm { c } } / E _ { \mathrm { c } , 2 8 } )\tag{5.2}
$$
  - `e5` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / B.5 Basic formulae for determining the creep coefficient: (1) The total mean creep coefficient $\varphi ( t , t _ { 0 } )$ may be calculated from Formula (B.5). For characteristic values of the creep coefficient, see (8).

$$
\varphi ( t , t _ { 0 } ) = \varphi _ { \mathrm { b c } } ( t , t _ { 0 } ) + \varphi _ { \mathrm { d c } } ( t , t _ { 0 } )\tag{B.5}
$$
  - `e6` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / B.6 Basic formulae for determining the shrinkage strain: (1) The total mean shrinkage or swelling strain $\varepsilon _ { \mathrm { c s } } ( t , t _ { s } )$ may be calculated from Formula (B.23). For characteristic values of shrinkage or swelling strain, see (4).

$$
\varepsilon _ { \mathrm { c s } } ( t , t _ { s } ) = \varepsilon _ { \mathrm { c b s } } ( t ) + \varepsilon _ { \mathrm { c d s } } ( t - t _ { s } )\tag{B.23}
$$

where shrinkage is subdivided into the basic shrinkage $\varepsilon _ { \mathrm { c b s } } ( t )$ which occurs even if no moisture loss is possible:

$$
\varepsilon _ { \mathrm { c b s } } ( t ) = \varepsilon _ { \mathrm { c b s , } f _ { \mathrm { c m } } } \cdot \beta _ { \mathrm { b s , t } } \cdot \alpha _ { \mathrm { N D P , b } }\tag{B.24}
$$

and the drying shrinkage $\varepsilon _ { \mathrm { c d s } } ( t , t _ { s } )$ giving the additional shrinkage if moisture loss occurs:
  - `e7` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 9.3.3 Simplified calculation of deflections for reinforced concrete building structures: (1) For rectangular sections, long-term deflections may be determined from linear elastic analysis using gross concrete sections and assuming long-term properties $\left( \mathrm { i } . \mathrm { e } . E _ { \mathrm { c , e f f } } \right)$ according to Formula (9.23).

$$
\delta = k _ { \mathrm { I } } [ \delta _ { l o a d s } + k _ { s } \delta _ { \varepsilon c s } ]\tag{9.23}
$$
  - `e8` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 9.3.4 General method for deflection calculations: (3) Members which are expected to crack, but may not be fully cracked, should be taken to behave in a manner intermediate between the uncracked and fully cracked conditions according to Formula (9.28):

$$
\alpha _ { \delta } = ( 1 - \zeta ) \alpha _ { \mathrm { I } } + \zeta \alpha _ { \mathrm { I I } }\tag{9.28}
$$
- [DISPUTED] `c1`: Claim is non-atomic: bundles (a) strength classes relate to characteristic 5% cylinder strength fck, and (b) reference age generally 28 days, 28-91 when project-specified. e1 (5.1.3(1), line 2241) verbatim supports only (a), ending at 'determined at an age t_ref.' The 28-day / 28-91 day content is in 5.1.3(2) at lines 2243-2247 but is NOT included in any cited evidence quote. Thus sub-claim (b) lacks supporting evidence; evidence set is insufficient / non-minimal. Fact itself is accurate to corpus but unevidenced.
- [ ] 人工确认最小充分证据集

## Q03: 有哪些因素会对混凝土的徐变与收缩产生影响?
- status: needs_human_review
- reference_answer: 混凝土徐变与收缩均受环境气候条件影响。对干燥收缩而言，构件尺寸、形状和温度会影响其发展；基本收缩与水灰比及由此关联的混凝土强度有关，且主要在早期硬化阶段发展。对干燥徐变而言，混凝土强度、环境相对湿度、构件名义尺寸、加载龄期及加载后的时间发展都会产生影响。
- `claim_1` [supported]: 环境气候条件会显著影响混凝土徐变和收缩这两类随时间发展的变形的大小及发展速率。
  evidence: evidence_1
- `claim_2` [supported]: 构件的尺寸和形状会影响干燥收缩；名义尺寸也会影响干燥徐变。
  evidence: evidence_2, evidence_3
- `claim_3` [supported]: 干燥徐变受混凝土强度、环境相对湿度、构件名义尺寸、加载时调整后的混凝土龄期，以及加载后的时间发展影响。
  evidence: evidence_3
- `claim_4` [supported]: 基本收缩与水灰比有关，因而也与混凝土强度有关；其大部分在浇筑后的早期硬化阶段发展。
  evidence: evidence_2
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / B.3 General: NOTE 1 Both creep and shrinkage are subdivided into two components, basic creep and drying creep or basic shrinkage and drying shrinkage, respectively, due to the pronounced effect of the ambient climate conditions on the magnitude and the kinetics of the time-dependent deformations.
  - `evidence_2` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / B.3 General: NOTE 2 The drying shrinkage strain develops slowly, since it is a function of the diffusion controlled migration of the water through the hardened concrete, which is affected by the size and shape, and the temperature of the member. The basic shrinkage strain develops during hardening of the concrete: the major part therefore develops in the early days after casting. Basic shrinkage is a function of the water/cement ratio and thus of the concrete strength.
  - `evidence_3` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / B.5 Basic formulae for determining the creep coefficient: $\beta _ { \mathrm { d c } , f _ { \mathrm { c m } } }$ is a function to describe the effect of concrete strength on drying creep, see Formula (B.10);

$\beta _ { \mathrm { d c , R H } }$ is a function to describe the effect of relative humidity and notional size on drying creep, see Formula (B.11);

$\boldsymbol { \beta } _ { \mathrm { d c } , t _ { 0 } }$ is a function to describe the effect of the adjusted concrete age at loading on drying creep, see Formula (B.12);

$\beta _ { \mathrm { d c } , t - t _ { 0 } }$ is a function to describe the time development of drying creep, see Formula (B.13);
- [ ] 人工确认最小充分证据集

## Q04: 钢筋的主要特性有哪些?并给出相应总结。
- status: needs_human_review
- reference_answer: 钢筋的主要特性可概括为：
- 强度：包括屈服强度、最大实际屈服强度和抗拉强度。
- 延性：以极限延伸率及抗拉强度/屈服强度比表征。
- 使用与构造性能：应有足够的可弯性和与混凝土的黏结能力；带肋钢筋的表面特征应保证黏结。
- 其他技术性能：截面尺寸及公差、疲劳强度、可焊性，以及焊接网和桁架筋的抗剪与焊接强度。

总结：Eurocode 2 对钢筋的要求并非仅限于强度，还同时覆盖延性、弯曲加工、混凝土黏结、尺寸控制、疲劳和焊接性能，以保证钢筋在混凝土结构中的设计与施工适用性。
- `claim_1` [supported]: 钢筋的主要力学特性包括屈服强度、最大实际屈服强度和抗拉强度。
  evidence: evidence_1
- `claim_2` [supported]: 钢筋应具有延性；规范以极限延伸率和抗拉强度与屈服强度之比表征该特性。
  evidence: evidence_1
- `claim_3` [supported]: 钢筋还应具备可弯性和与混凝土的黏结特性；带肋钢筋的表面应保证足够黏结。
  evidence: evidence_2
- `claim_4` [supported]: 钢筋的主要技术特性还包括截面尺寸及公差、疲劳强度、可焊性，以及焊接网和桁架筋的抗剪与焊接强度。
  evidence: evidence_3
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.2.2 Properties: (1)P The behaviour of reinforcing steel is specified by the following properties:

\- yield strength $( f _ { \mathrm { y k } } \circ \mathsf { r } f _ { 0 , 2 \mathrm { k } } )$

\- maximum actual yield strength $( \pmb { f } _ { \mathsf { y } , \mathsf { m a x } } )$

\- tensile strength (ft)

\- ductility $( \varepsilon _ { \mathsf { u k } }$ and $f _ { \mathrm { t } } / f _ { \mathrm { y k } } )$
  - `evidence_2` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.2.2 Properties: (4)P The surface characteristics of ribbed bars shall be such to ensure adequate bond with the concrete.

(5) Adequate bond may be assumed by compliance with the specification of projected rib area, $\pmb { f } _ { \mathsf { R } } .$

Note: Minimum values of the relative rib area, $\pmb { f } _ { \mathrm { R } } ,$ , are given in the Annex C.

(6)P The reinforcement shall have adequate bendability to allow the use of the minimum mandrel diameters specified in Table 8.1 and to allow rebending to be carried out.
  - `evidence_3` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.2.2 Properties: \- bendability

\- bond characteristics $( { f } _ { \mathsf { R } } ;$ See Annex C)

\- section sizes and tolerances

\- fatigue strength

\- weldability

\- shear and weld strength for welded fabric and lattice girders
- [ ] 人工确认最小充分证据集

## Q05: 请问都有那些环境暴露等级?
- status: needs_human_review
- reference_answer: 按 BS EN 1992-1-1:2023 表 6.1，环境暴露等级分为七类：X0（无腐蚀或侵蚀风险）；XC1–XC4（碳化引起的埋置金属腐蚀）；XD1–XD3（氯化物、不含海水引起的埋置金属腐蚀）；XS1–XS3（海水氯化物引起的埋置金属腐蚀）；XF1–XF4（冻融侵蚀）；XA1–XA3（化学侵蚀）；XM1–XM3（混凝土磨蚀的机械侵蚀）。
- `claim_1` [supported]: 环境暴露等级包括无腐蚀或侵蚀风险等级 X0。
  evidence: evidence_1
- `claim_2` [supported]: 环境暴露等级包括由碳化引起的埋置金属腐蚀等级：XC1、XC2、XC3、XC4。
  evidence: evidence_2
- `claim_3` [supported]: 环境暴露等级包括由氯化物（不含海水）引起的埋置金属腐蚀等级：XD1、XD2、XD3。
  evidence: evidence_3
- `claim_4` [supported]: 环境暴露等级包括由海水氯化物引起的埋置金属腐蚀等级：XS1、XS2、XS3。
  evidence: evidence_4
- `claim_5` [supported]: 环境暴露等级包括冻融侵蚀等级：XF1、XF2、XF3、XF4。
  evidence: evidence_5
- `claim_6` [supported]: 环境暴露等级包括化学侵蚀等级：XA1、XA2、XA3。
  evidence: evidence_6
- `claim_7` [supported]: 环境暴露等级包括混凝土受磨蚀的机械侵蚀等级：XM1、XM2、XM3。
  evidence: evidence_7
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / (3) Table 6.1 defines exposure classes X for the most common environmental exposure conditions.: <tr><td colspan="3" rowspan="1">1. No risk of corrosion or attack</td></tr><tr><td colspan="3" rowspan="1">For concrete without reinforcement or embedded metal:</td></tr><tr><td colspan="1" rowspan="1">X0</td>
  - `evidence_2` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / (3) Table 6.1 defines exposure classes X for the most common environmental exposure conditions.: <tr><td colspan="3" rowspan="1">2. Corrosion of embedded metal induced by carbonation</td></tr><tr><td colspan="3" rowspan="1">Where concrete containing steel reinforcement or other embedded metal is exposed to air and moisture, theexposure should be classified as follows:</td></tr><tr><td colspan="1" rowspan="1">XC1</td><td colspan="1" rowspan="1">Dry.</td><td colspan="1" rowspan="1">Concrete inside buildings with low air humidity,where the corrosion rate will be insignificant.</td></tr><tr><td colspan="1" rowspan="1">XC2</td><td colspan="1" rowspan="1">Wet or permanent high humidity, rarely dry.</td><td colspan="1" rowspan="1">Concrete surfaces subject to long-term watercontact or permanently submerged in water orpermanently exposed to high humidity;many foundations; water containments (notexternal).NOTE 1 Leaching could also cause corrosion (see (5), and(6), XA classes).</td></tr><tr><td colspan="1" rowspan="1">XC3</td><td colspan="1" rowspan="1">Moderate humidity.</td><td colspan="1" rowspan="1">Concrete inside buildings with moderate humidityand not permanent high humidity;External concrete sheltered from rain.</td></tr><tr><td colspan="1" rowspan="1">XC4</td>
  - `evidence_3` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / (3) Table 6.1 defines exposure classes X for the most common environmental exposure conditions.: <tr><td colspan="3" rowspan="1">3. Corrosion of embedded metal induced by chlorides, excluding sea water</td></tr><tr><td colspan="3" rowspan="1">Where concrete containing steel reinforcement or other embedded metal is subject to contact with watercontaining chlorides, including de-icing salts, from sources other than from sea water, the exposure should beclassified as follows:</td></tr><tr><td colspan="1" rowspan="1">XD1</td><td colspan="1" rowspan="1">Moderate humidity</td><td colspan="1" rowspan="1">Concrete surfaces exposed to airborne chlorides.</td></tr><tr><td colspan="1" rowspan="1">XD2</td><td colspan="1" rowspan="1">Wet, rarely dry.</td><td colspan="1" rowspan="1">Swimming pools;Concrete components exposed to industrial waterscontaining chlorides.NOTE 2 If the chloride content of the water is sufficientlylow then XD1 applies.</td></tr><tr><td colspan="1" rowspan="1">XD3</td>
  - `evidence_4` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / (3) Table 6.1 defines exposure classes X for the most common environmental exposure conditions.: <tr><td colspan="3" rowspan="1">4. Corrosion of embedded metal induced by chlorides from sea water</td></tr><tr><td colspan="3" rowspan="1">Where concrete containing steel reinforcement or other embedded metal is subject to contact with chloridesfrom sea water or air carrying salt originating from sea water, the exposure should be classified as follows:</td></tr><tr><td colspan="1" rowspan="1">XS1</td><td colspan="1" rowspan="1">Exposed to airborne salt but not in direct contactwith sea water.</td><td colspan="1" rowspan="1">Structures near to or on the coast.</td></tr><tr><td colspan="1" rowspan="1">XS2</td><td colspan="1" rowspan="1">Permanently submerged.</td><td colspan="1" rowspan="1">Parts of marine structures and structures inseawater.</td></tr><tr><td colspan="1" rowspan="1">XS3</td>
  - `evidence_5` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / (3) Table 6.1 defines exposure classes X for the most common environmental exposure conditions.: <tr><td colspan="3" rowspan="1">5. Freeze/Thaw Attack</td></tr><tr><td colspan="3" rowspan="1">Where concrete is exposed to significant attack by freeze/thaw cycles whilst wet, the exposure should beclassified as follows. A XF-classification is not necessary in cases where freeze/thaw cycles are rare.</td></tr><tr><td colspan="1" rowspan="1">XF1</td><td colspan="1" rowspan="1">Moderate water saturation, without de-icing agent.</td><td colspan="1" rowspan="1">Vertical concrete surfaces exposed to rain andfreezing.</td></tr><tr><td colspan="1" rowspan="1">XF2</td><td colspan="1" rowspan="1">Moderate water saturation, with de-icing agent.</td><td colspan="1" rowspan="1">Vertical concrete surfaces of road structuresexposed to freezing and airborne de-icing agents.</td></tr><tr><td colspan="1" rowspan="1">XF3</td><td colspan="1" rowspan="1">High water saturation, without de-icing agents.</td><td colspan="1" rowspan="1">Horizontal concrete surfaces exposed to rain andfreezing.</td></tr><tr><td colspan="1" rowspan="1">XF4</td>
  - `evidence_6` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / (3) Table 6.1 defines exposure classes X for the most common environmental exposure conditions.: <tr><td colspan="3" rowspan="1">6. Chemical attack</td></tr><tr><td colspan="3" rowspan="1">Where concrete is exposed to chemical attack from natural soils and ground water, the exposure should beclassified as follows:</td></tr><tr><td colspan="1" rowspan="1">XA1</td><td colspan="1" rowspan="1">Slightly aggressive chemical environment.</td><td colspan="1" rowspan="1">Natural soils and ground water according toTable 6.2.</td></tr><tr><td colspan="1" rowspan="1">XA2</td><td colspan="1" rowspan="1">Moderately aggressive chemical environment.</td><td colspan="1" rowspan="1">Natural soils and ground water according toTable 6.2.</td></tr><tr><td colspan="1" rowspan="1">XA3</td>
  - `evidence_7` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / (3) Table 6.1 defines exposure classes X for the most common environmental exposure conditions.: <tr><td colspan="3" rowspan="1">7. Mechanical attack of concrete by abrasion</td></tr><tr><td colspan="3" rowspan="1">Where concrete is exposed to mechanical abrasion, the exposure should be classified as follows:</td></tr><tr><td colspan="1" rowspan="1">XM1</td><td colspan="1" rowspan="1">Moderate abrasion.</td><td colspan="1" rowspan="1">Members of industrial sites frequented by vehicleswith pneumatic tyres.</td></tr><tr><td colspan="1" rowspan="1">XM2</td><td colspan="1" rowspan="1">Heavy abrasion.</td><td colspan="1" rowspan="1">Members of industrial sites frequented by fork liftswith pneumatic or solid rubber tyres.</td></tr><tr><td colspan="1" rowspan="1">XM3</td>
- [ ] 人工确认最小充分证据集

## Q06: 保护层都与什么因素相关，该怎么计算?
- status: review_not_converged
- reference_answer: 保护层需兼顾粘结传力、防腐耐久和耐火。先依据暴露等级与结构等级确定耐久性最小值 c_min,dur；推荐结构等级会因100年设计工作寿命、混凝土强度等级、满足条件的板式构件几何及混凝土生产特殊质量控制而调整。随后计算 c_min = max{c_min,b；c_min,dur + Δc_dur,γ − Δc_dur,st − Δc_dur,add；10 mm}。最后取名义保护层 c_nom = c_min + Δc_dev；Δc_dev 是施工偏差的设计预留，推荐10 mm。设计计算和图纸通常采用该名义值，除非另有规定。
- `claim_1` [supported]: 最小混凝土保护层用于确保粘结力安全传递、钢筋防腐耐久性及足够的耐火性能。
  evidence: evidence_1
- `claim_2` [supported]: 最小保护层按公式(4.2)取三者最大值：粘结要求的 c_min,b、耐久性项 c_min,dur + Δc_dur,γ − Δc_dur,st − Δc_dur,add，以及 10 mm。
  evidence: evidence_2
- `claim_3` [supported]: 耐久性最小保护层 c_min,dur 考虑暴露等级和结构等级；推荐结构等级可因100年设计工作寿命、混凝土强度等级、满足条件的板式构件几何和混凝土生产特殊质量控制而调整。
  evidence: evidence_3
- `claim_4` [supported]: 名义保护层按 c_nom = c_min + Δc_dev 计算；Δc_dev 为施工偏差的设计预留，推荐值为10 mm。
  evidence: evidence_4
- `claim_5` [supported]: 设计计算和图纸通常采用名义保护层，除非明确规定采用其他保护层数值。
  evidence: evidence_5
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 4.4.1.2 Minimum cover, $\pmb { c } _ { \mathrm { m i n } }$: (1)P Minimum concrete cover, $c _ { \mathsf { m i n } } ,$ shall be provided in order to ensure:

\- the safe transmission of bond forces (see also Sections 7 and 8)

\- the protection of the steel against corrosion (durability)

an adequate fire resistance (see EN 1992-1-2)
  - `evidence_2` EN1992-1-1_2004/EN1992-1-1_2004.md / 4.4.1.2 Minimum cover, $\pmb { c } _ { \mathrm { m i n } }$: (2)P The greater value for $c _ { \mathsf { m i n } }$ satisfying the requirements for both bond and environmental conditions shall be used.

$$
c _ { \operatorname* { m i n } } = \operatorname* { m a x } { \{ c _ { \operatorname* { m i n } , \mathrm { b } } ; \mathrm { ~ } c _ { \operatorname* { m i n } , \mathrm { d u r } } + \Delta c _ { \mathrm { d u r } , \gamma } - \Delta c _ { \mathrm { d u r } , \mathrm { s t } } - \Delta c _ { \mathrm { d u r } , \mathrm { a d d } } ; \mathrm { ~ } 1 0 \mathrm { ~ m m } \} }\tag{4.2}
$$
  - `evidence_3` EN1992-1-1_2004/EN1992-1-1_2004.md / 4.4.1.2 Minimum cover, $\pmb { c } _ { \mathrm { m i n } }$: (5) The minimum cover values for reinforcement and prestressing tendons in normal weight concrete taking account of the exposure classes and the structural classes is given by cmin,dur.

Note: Structural classification and values of $c _ { \mathrm { m i n , d u r } }$ for use in a Country may be found in its National Annex. The recommended Structural Class (design working life of 50 years) is S4 for the indicative concrete strengths given in Annex E and the recommended modifications to the structural class is given in Table 4.3N. The recommended minimum Structural Class is S1.

The recommended values of $c _ { \mathrm { m i n , d u r } }$ are given in Table 4.4N (reinforcing steel) and Table 4.5N (prestressing steel).

Table 4.3N: Recommended structural classification
<table><tr><td rowspan=1 colspan=8>Structural Class</td></tr><tr><td rowspan=2 colspan=1>Criterion</td><td rowspan=1 colspan=7>Exposure Class according to Table 4.1</td></tr><tr><td rowspan=1 colspan=1>x0</td><td rowspan=1 colspan=1>XC1</td><td rowspan=1 colspan=1>XC2/XC3</td><td rowspan=1 colspan=1>XC4</td><td rowspan=1 colspan=1>XD1</td><td rowspan=1 colspan=1>XD2/XS1</td><td rowspan=1 colspan=1>XD3/XS2/XS3</td></tr><tr><td rowspan=1 colspan=1>Design Working Life of100years</td><td rowspan=1 colspan=1>increaseclass by 2</td><td rowspan=1 colspan=1>increaseclass by 2</td><td rowspan=1 colspan=1>increaseclass by 2</td><td rowspan=1 colspan=1>increaseclass by 2</td><td rowspan=1 colspan=1>increaseclass by2</td><td rowspan=1 colspan=1>increaseclass by 2</td><td rowspan=1 colspan=1>increase classby2</td></tr><tr><td rowspan=1 colspan=1>Strength Class1)2</td><td rowspan=1 colspan=1>≥ C30/37reduceclass by 1</td><td rowspan=1 colspan=1>≥ C30/37reduceclass by 1</td><td rowspan=1 colspan=1>≥ C35/45reduceclass by 1</td><td rowspan=1 colspan=1>≥ C40/50reduceclass by 1</td><td rowspan=1 colspan=1>≥ C40/50reduceclass by 1</td><td rowspan=1 colspan=1>≥ C40/50reduceclass by 1</td><td rowspan=1 colspan=1>≥ C45/55reduce class by1</td></tr><tr><td rowspan=1 colspan=1>Memberwith slabgeometry(position of reinforcementnot affected by constructionprocess)</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduce class by1</td></tr><tr><td rowspan=1 colspan=1>Special QualityControl of the concreteproduction ensured</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduceclass by 1</td><td rowspan=1 colspan=1>reduce class by1</td></tr></table>
  - `evidence_4` EN1992-1-1_2004/EN1992-1-1_2004.md / 4.4.1.1 General: (2)P The nominal cover shall be specified on the drawings. It is defined as a minimum cover, $c _ { \mathsf { m i n } }$ (see 4.4.1.2), plus an allowance in design for deviation, $\Delta c _ { \mathsf { d e v } }$ (see 4.4.1.3):

$$
c _ { \mathrm { n o m } } = c _ { \mathrm { m i n } } + \Delta c _ { \mathrm { d e v } }\tag{4.1}
$$

## 4.4.1.3 Allowance in design for deviation

(1)P To calculate the nominal cover, $c _ { \mathsf { n o m } } ,$ , an addition to the minimum cover shall be made in design to allow for the deviation $( \Delta c _ { \mathsf { d e v } } )$ . The required minimum cover shall be increased by the absolute value of the accepted negative deviation.

Note: The value of $\Delta c _ { \mathrm { d e v } }$ for use in a Country may be found in its National Annex. The recommended value is 10 mm.
  - `evidence_5` EN1992-1-1_2004/EN1992-1-1_2004.md / 4.4.1.3 Allowance in design for deviation: (2) For Buildings, ENV 13670-1 gives the acceptable deviation. This is normally also sufficient for other types of structures. It should be considered when choosing the value of nominal cover for design. The nominal value of cover for design should be used in the calculations and stated on the drawings, unless a value other than the nominal cover is specified (e.g. minimum value).
- [ ] 人工确认最小充分证据集

## Q07: 结构分析的目的是什么?
- status: needs_human_review
- reference_answer: 结构分析的目的是确定结构每一点的作用效应。
- `claim_1` [supported]: 结构分析的目的是确定结构每一点的作用效应。
  evidence: evidence_1
  - `evidence_1` EN1990_2002/EN1990_2002.md / structural analysis: procedure or algorithm for determination of action effects in every point of a structure
- [ ] 人工确认最小充分证据集

## Q08: 在哪些部位当线性应变分布的假设不成立时，可能需要进行局部分析?
- status: review_not_converged
- reference_answer: 当线性应变分布的假设不成立时，可能需要在支座附近、集中荷载局部区域、梁柱节点处、锚固区和截面变化处进行局部分析。
- `claim_1` [supported]: 在线性应变分布假设不成立的支座附近，可能需要进行局部分析。
  evidence: evidence_1
- `claim_2` [supported]: 在线性应变分布假设不成立的集中荷载局部区域，可能需要进行局部分析。
  evidence: evidence_1
- `claim_3` [supported]: 在线性应变分布假设不成立的梁柱节点处，可能需要进行局部分析。
  evidence: evidence_1
- `claim_4` [supported]: 在线性应变分布假设不成立的锚固区，可能需要进行局部分析。
  evidence: evidence_1
- `claim_5` [supported]: 在线性应变分布假设不成立的截面变化处，可能需要进行局部分析。
  evidence: evidence_1
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / ## 5.1.1 General requirements: (2) Local analyses may be necessary where the assumption of linear strain distribution is not valid, e.g.:

in the vicinity of supports

local to concentrated loads

in beam-column intersections

in anchorage zones

at changes in cross section.
- [ ] 人工确认最小充分证据集

## Q09: 根据性质和功能，结构构件包括哪些类型?
- status: needs_human_review
- reference_answer: 根据性质和功能，结构构件包括梁、柱、板、墙、平板、拱、壳等类型。
- `claim_1` [supported]: 按构件的性质和功能，结构构件可分为梁、柱、板、墙、平板、拱、壳等类型。
  evidence: evidence_1
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 5.3.1 Structural models for overall analysis: (1)P The elements of a structure are classified, by consideration of their nature and function, as beams, columns, slabs, walls, plates, arches, shells etc. Rules are provided for the analysis of the commoner of these elements and of structures consisting of combinations of these elements.
- [ ] 人工确认最小充分证据集

## Q10: 什么是单向板?
- status: needs_human_review
- reference_answer: 单向板（单向受力板）是指在以均布荷载为主时，可按单向跨越处理的板。Eurocode 2 给出的两种情形是：板具有两条自由且大致平行的边；或四边支承的近似矩形板中央部分，其长跨与短跨之比大于 2。
- `claim_1` [supported]: 在以均布荷载为主时，具有两条自由（无支承）且大致平行边的板，可视为单向受力板。
  evidence: evidence_1
- `claim_2` [supported]: 在以均布荷载为主时，四边支承的近似矩形板若长跨与短跨之比大于2，其中央部分可视为单向受力板。
  evidence: evidence_2
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 5.3.1 Structural models for overall analysis: (5) A slab subjected to dominantly uniformly distributed loads may be considered to be oneway spanning if either:

\- it possesses two free (unsupported) and sensibly parallel edges, or
  - `evidence_2` EN1992-1-1_2004/EN1992-1-1_2004.md / 5.3.1 Structural models for overall analysis: \- it is the central part of a sensibly rectangular slab supported on four edges with a ratio of the longer to shorter span greater than 2.
- [ ] 人工确认最小充分证据集

## Q11: 欧标的截面计算的基本假设前提是什么？
- status: needs_human_review
- reference_answer: 按语料中的 EN 1992-1-1 截面弯曲计算规则，基本前提适用于加载前后截面近似保持平面的梁、板等构件非扰动区。计算钢筋混凝土或预应力混凝土截面的极限弯矩承载力时：平截面保持平面；有粘结钢筋或有粘结预应力筋与周围混凝土的应变变化相同；忽略混凝土抗拉强度；受压混凝土和钢筋（或预应力钢材）的应力分别采用规定的设计应力分布及设计应力—应变关系；预应力筋应力评估还应考虑其与周围混凝土的应变差和相应时刻的时变损失。
- `claim_1` [supported]: 对于钢筋混凝土或预应力混凝土截面的极限弯矩承载力计算，适用对象是加载前后截面近似保持平面的梁、板及类似构件的非扰动区。
  evidence: evidence_1
- `claim_2` [supported]: 截面计算假定平截面保持平面。
  evidence: evidence_2
- `claim_3` [supported]: 假定有粘结钢筋或有粘结预应力筋与其周围混凝土的应变变化相同，不论受拉或受压。
  evidence: evidence_3
- `claim_4` [supported]: 计算时忽略混凝土抗拉强度。
  evidence: evidence_4
- `claim_5` [supported]: 受压混凝土应力取自规定的设计应力分布；钢筋或预应力钢材应力取自规定的设计应力—应变关系。
  evidence: evidence_5
- `claim_6` [supported]: 评估预应力筋应力时，应考虑预应力钢材与周围混凝土的应变差，并适当计入计算时刻的时变损失。
  evidence: evidence_6
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.1.1 General: (1) 8.1 applies to undisturbed regions of beams, slabs and similar types of members for which plane sections remain approximately plane before and after loading. The discontinuity regions of beams and other members in which plane sections do not remain plane may be designed and detailed according to the general approach provided in 8.5.
  - `evidence_2` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.1.1 General: (2) When determining the ultimate moment resistance of reinforced or prestressed concrete crosssections, the following assumptions shall be made:

— plane sections remain plane;
  - `evidence_3` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.1.1 General: — the change in strain in bonded reinforcing steel or bonded prestressing tendons, whether in tension or in compression, is the same as the change in strain in the surrounding concrete;
  - `evidence_4` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.1.1 General: — the tensile strength of concrete is ignored;

— the stresses in the concrete in compression are derived from the design stress distributions given in 8.1.2;
  - `evidence_5` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.1.1 General: — the stresses in the concrete in compression are derived from the design stress distributions given in 8.1.2;

— the stresses in the reinforcing or prestressing steel are derived from the design stress-strain relationships in 5.2 (Figure 5.2) and 5.3 (Figure 5.3);
  - `evidence_6` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.1.1 General: the strain difference between prestressing steel and surrounding concrete is considered when assessing the stresses in the tendons with due regard to time-dependent losses at the time considered.
- [ ] 人工确认最小充分证据集

## Q12: 混凝土受压区应变-应力分布假设是什么？
- status: needs_human_review
- reference_answer: 混凝土受压区按平截面假定处理，因此应变沿截面线性分布。受压混凝土的设计应力分布可采用抛物线—矩形关系：压应变从零至 εc2 时应力按抛物线关系取值，εc2 至 εcu 时应力为 fcd；也可替代采用矩形应力块。
- `claim_1` [supported]: 极限弯曲截面采用平截面假定；受压区应变沿截面线性分布。
  evidence: evidence_1
- `claim_2` [supported]: 受压混凝土可采用抛物线—矩形设计应力分布：当压应变为 0 至 εc2 时，应力按抛物线关系取值；当压应变为 εc2 至 εcu 时，应力为 fcd。
  evidence: evidence_2
- `claim_3` [supported]: 也可替代采用图 8.2d 所示的矩形应力块分布。
  evidence: evidence_3
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.1.1 General: (2) When determining the ultimate moment resistance of reinforced or prestressed concrete crosssections, the following assumptions shall be made:

— plane sections remain plane;
  - `evidence_2` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.1.2 Stress distribution in the compression zones: (1) For the design of cross-sections, the following stress distribution may be used, see Figure 8.2c) (compressive strain shown positive):

$$
\sigma _ { \mathrm { c d } } = \left\{ \begin{array} { c } { f _ { \mathrm { c d } } \left[ 1 - \left( 1 - \frac { \varepsilon _ { \mathrm { c } } } { \varepsilon _ { \mathrm { c } 2 } } \right) ^ { 2 } \right] } \\ { f _ { \mathrm { c d } } } \end{array} \right.
$$

$$
\mathrm { f o r } 0 \le \varepsilon _ { \mathrm { c } } \le \varepsilon _ { \mathrm { c } 2 }
$$

$$
\mathrm { f o r } \varepsilon _ { \mathrm { c } 2 } \leq \varepsilon _ { \mathrm { c } } \leq \varepsilon _ { \mathrm { c u } }\tag{8.4}
$$
  - `evidence_3` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.1.2 Stress distribution in the compression zones: (2) Alternatively, a rectangular stress block distribution as given in Figure 8.2d) may be assumed.
- [ ] 人工确认最小充分证据集

## Q13: 混凝土压碎应变限值是多少？
- status: needs_human_review
- reference_answer: 混凝土压碎（极限压缩）应变限值 εcu1 按 2.8 + 14·(1 − fcm/108)^4（‰）计算，最大为 3.5‰。
- `claim_1` [supported]: 按 EN 1992-1-1:2023，对短期单轴受压混凝土，极限压缩（压碎）应变 εcu1 按 2.8 + 14·(1 − fcm/108)^4（‰）计算，且不超过 3.5‰。
  evidence: evidence_1
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 5.1.6 Design assumptions: $$
\varepsilon _ { \mathrm { c } } < \varepsilon _ { \mathrm { c u 1 } } [ \% _ { 0 } ] = 2 , 8 + 1 4 \cdot ( 1 - f _ { \mathrm { c m } } / 1 0 8 ) ^ { 4 } \leq 3 , 5 \ \%\tag{5.10}
$$
- [ ] 人工确认最小充分证据集

## Q14: 极限受力状态下混凝土受压区高度限值为多少？
- status: needs_human_review
- reference_answer: 在屈服铰区域，极限受力状态下混凝土受压区高度以中性轴深度 x_u 表示：C50/60 及以下，x_u/d ≤ 0.45；C55/67 及以上，x_u/d ≤ 0.35。
- `claim_1` [supported]: 在屈服铰区域，极限状态中性轴深度（即受压区高度）与有效高度之比 x_u/d：混凝土强度等级不高于 C50/60 时不得超过 0.45；不低于 C55/67 时不得超过 0.35。
  evidence: evidence_1
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 5.6.3 Rotation capacity: (2) In regions of yield hinges, $x _ { \mathrm { u } } / d$ shall not exceed the value 0,45 for concrete strength classes less than or equal to C50/60, and 0,35 for concrete strength classes greater than or equal to C55/67.
- [ ] 人工确认最小充分证据集

## Q15: 弯矩重分布限值为多少？
- status: needs_human_review
- reference_answer: 按所给 Eurocode 2:2023 语料，在无显式转动能力验算的弯矩重分布中，δ_M（重分布后弯矩与弹性弯矩之比）的下限：B/C 级钢筋或预应力钢材为 0.7，A 级钢筋为 0.8。
- `claim_1` [supported]: 在所给 Eurocode 2:2023 语料的无显式转动能力验算方法中，弯矩重分布后弯矩与弹性弯矩之比 δ_M 的下限为：采用 B 级或 C 级钢筋（或预应力钢材）时不小于 0.7；采用 A 级钢筋时不小于 0.8。
  evidence: evidence_1
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 7.3.2 Linear elastic analysis with redistribution: $\geq 0 , 7$ where Class B or Class C reinforcing steel or prestressing steel is used (see Table 5.5);

$\ge 0 , 8$ where Class A reinforcing steel is used (see Table 5.5).
- [ ] 人工确认最小充分证据集

## Q16: fcd 如何计算
- status: needs_human_review
- reference_answer: fcd（混凝土设计抗压强度）按 `fcd = αcc·fck/γC` 计算。αcc 考虑长期效应和荷载施加方式的不利影响；其国家取值应在 0.8～1.0，推荐为 1.0。γC 应按国家附录和设计状况选取；该规范表中的推荐值为：持久/暂态设计状况 1.5，偶然设计状况 1.2。
- `claim_1` [supported]: 混凝土设计抗压强度按 fcd = αcc·fck/γC 计算；其中 αcc 考虑长期效应及荷载施加方式造成的不利影响。
  evidence: evidence_1
- `claim_2` [supported]: αcc 的国家取值应在 0.8 至 1.0 之间，推荐值为 1.0。
  evidence: evidence_2
- `claim_3` [supported]: γC 是混凝土分项安全系数；表中推荐持久和暂态设计状况取 1.5，偶然设计状况取 1.2。
  evidence: evidence_3
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.6 Design compressive and tensile strengths: (1)P The value of the design compressive strength is defined as

$$
f _ { \mathrm { c d } } = \alpha _ { \mathrm { c c } } f _ { \mathrm { c k } } / \gamma _ { \mathrm { C } }\tag{3.15}
$$

where:

C is the partial safety factor for concrete, see 2.4.2.4, and

$\alpha _ { \mathsf { c c } }$ is the coefficient taking account of long term effects on the compressive strength and of unfavourable effects resulting from the way the load is applied.
  - `evidence_2` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.6 Design compressive and tensile strengths: Note: The value of $\scriptstyle { \mathfrak { a } } _ { \mathtt { C C } }$ for use in a Country should lie between 0,8 and 1,0 and may be found in its National Annex. The recommended value is 1.
  - `evidence_3` EN1992-1-1_2004/EN1992-1-1_2004.md / 2.4.2.4 Partial factors for materials: (1) Partial factors for materials for ultimate limit states, $\textstyle \gamma _ { \mathsf { C } }$ and $\gamma _ { \mathsf { S } }$ should be used.

Note: The values of C and $\gamma _ { \mathsf { S } }$ for use in a Country may be found in its National Annex. The recommended values for ‘persistent & transient’ and ‘accidental, design situations are given in Table 2.1N. These are not valid for fire design for which reference should be made to EN 1992-1-2.

For fatigue verification the partial factors for persistent design situations given in Table 2.1N are recommended for the values of $\gamma _ { \mathsf { C } , \mathsf { f a t } } \mathsf { a n d }$ $\gamma _ { \mathsf { S } , \mathsf { f a t } }$

Table 2.1N: Partial factors for materials for ultimate limit states
<table><tr><td rowspan=1 colspan=1>Design situations</td><td rowspan=1 colspan=1>Yc for concrete</td><td rowspan=1 colspan=1>Ys for reinforcing steel</td><td rowspan=1 colspan=1>Yys for prestressing steel</td></tr><tr><td rowspan=1 colspan=1>Persistent&amp;Transient</td><td rowspan=1 colspan=1>1.5</td><td rowspan=1 colspan=1>1,15</td><td rowspan=1 colspan=1>1,15</td></tr><tr><td rowspan=1 colspan=1>Accidental</td><td rowspan=1 colspan=1>1,2</td><td rowspan=1 colspan=1>1,0</td><td rowspan=1 colspan=1>1.0</td></tr></table>
- [ ] 人工确认最小充分证据集

## Q17: 截面计算中材料分项安全系数为多少？
- status: needs_human_review
- reference_answer: 截面承载力计算通常采用持久和短暂设计状况：混凝土材料分项系数 γc=1.50，钢筋和预应力钢 γs=1.15；对无抗剪钢筋的抗剪和冲切承载力，γv=1.40。事故设计状况分别为 γs=1.00、γc=1.15、γv=1.15；正常使用极限状态 γs=γc=1.00。
- `c1` [supported]: 按 EN 1992-1-1:2023 的持久和短暂设计状况，混凝土 γc=1.50，钢筋和预应力钢 γs=1.15；无抗剪钢筋的抗剪和冲切承载力 γv=1.40。
  evidence: e1
- `c2` [supported]: 事故设计状况下，γs=1.00、γc=1.15、γv=1.15；正常使用极限状态下，γs=γc=1.00。
  evidence: e1
  - `e1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 4.3.3 Partial factors for materials: <table><tr><td rowspan=1 colspan=1>Design situations —Limit states</td><td rowspan=1 colspan=1>γs for reinforcing andprestressing steel</td><td rowspan=1 colspan=1>γcand $\gamma _ { \mathbf { C E } }$ forconcrete</td><td rowspan=1 colspan=1>γv for shear and punchingresistance without shearreinforcement</td></tr><tr><td rowspan=1 colspan=1>Persistent and transientdesign situation</td><td rowspan=1 colspan=1>1,15</td><td rowspan=1 colspan=1>1,50ª</td><td rowspan=1 colspan=1>1,40</td></tr><tr><td rowspan=1 colspan=1>Fatigue design situation</td><td rowspan=1 colspan=1>1,15</td><td rowspan=1 colspan=1>1,50</td><td rowspan=1 colspan=1>1,40</td></tr><tr><td rowspan=1 colspan=1>Accidental design situation</td><td rowspan=1 colspan=1>1,00</td><td rowspan=1 colspan=1>1,15</td><td rowspan=1 colspan=1>1,15</td></tr><tr><td rowspan=1 colspan=1>Serviceability limit state</td><td rowspan=1 colspan=1>1,00</td><td rowspan=1 colspan=1>1,00</td><td rowspan=1 colspan=1></td></tr><tr><td rowspan=1 colspan=4>NOTE The partial factors for materials correspond to geometrical deviations of Tolerance Class 1 andExecution Class 2 in EN 13670.</td></tr><tr><td rowspan=1 colspan=4>a  The value for γce applies when the indicative value for the elastic modulus according 5.1.4(2) is used. A valueγcE = 1,3 applies when the elastic modulus is determined according to 5.1.4(1).</td></tr></table>
- [ ] 人工确认最小充分证据集

## Q18: 混凝土抗压强度标准值、设计值与平均强度之间是什么关系？
- status: review_not_converged
- reference_answer: 📐【HelloAGENTS】- 简化流程：评估

📋 需求: 重新检索指定只读 Markdown 语料，并输出完整替换版 Eurocode gold；重点修正 `document_path` 为相对路径。

📊 评分: 8/10（任务目标 3/3 | 完成标准 3/3 | 涉及范围 2/2 | 限制条件 0/2）

🔄 下一步: 请回复“确认”，我将直接检索全语料并生成完整替换版 gold。
- [ ] 人工确认最小充分证据集

## Q19: 钢筋的锚固长度与搭接长度受哪些因素影响？
- status: review_not_converged
- reference_answer: 钢筋锚固长度主要由钢筋直径、设计钢筋应力、混凝土强度、有效保护层/间距参数 c_d 以及浇筑形成的粘结条件决定；横向或约束钢筋及外部压力也会影响其取值，并可在规定条件下缩短锚固长度。搭接长度以锚固长度乘搭接系数 k_ls 为基础，故继承上述影响因素；此外还受搭接钢筋净距、搭接是否跨越塑性铰区、同一截面的搭接比例及错开布置情况影响。
- `claim_1` [supported]: 直锚钢筋的设计锚固长度受钢筋直径、设计钢筋应力、混凝土抗压强度以及有效保护层/间距参数 c_d 影响。
  evidence: evidence_1
- `claim_2` [supported]: 浇筑形成的粘结条件会影响锚固长度；不良粘结条件采用比良好粘结条件更大的系数。
  evidence: evidence_2
- `claim_3` [supported]: 满足规定布置条件的约束或横向钢筋，以及外部压力，可通过改变约束条件而减小设计锚固长度。
  evidence: evidence_3
- `claim_4` [supported]: 搭接长度至少取第 11.4 条锚固长度乘搭接系数 k_ls，因此锚固长度的相关影响因素会传递至搭接长度。
  evidence: evidence_4
- `claim_5` [supported]: 搭接长度还受搭接钢筋净距影响；当受拉搭接跨越塑性铰区时，约束钢筋、错开搭接、同一截面的搭接钢筋比例及相邻搭接距离会影响可采用的设计应力和长度要求。
  evidence: evidence_5, evidence_6
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 11.4.2 Anchorage of straight bars: l _ { \mathrm { b d } } = k _ { \mathrm { l b } } \cdot k _ { \mathrm { c p } } \cdot \phi \cdot \Big ( \frac { \sigma _ { \mathrm { s d } } } { 4 3 5 } \Big ) ^ { n _ { \sigma } } \cdot \Big ( \frac { 2 5 } { f _ { \mathrm { c k } } } \Big ) ^ { \frac { 1 } { 2 } } \cdot \Big ( \frac { \phi } { 2 0 } \Big ) ^ { \frac { 1 } { 3 } } \cdot \Big ( \frac { 1 , 5 \phi } { c _ { \mathrm { d } } } \Big ) ^ { \frac { 1 } { 2 } } \geq 1 0 \phi\tag{11.3}
  - `evidence_2` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 11.4.2 Anchorage of straight bars: $k _ { \mathrm { c p } } = 1 , 0$ for bars with good bond conditions according to (4);

$k _ { \mathrm { c p } } = 1 , 2$ for poor bond conditions and for all bars used in slipform construction unless it is shown that the vertical bars cannot move during casting;
  - `evidence_3` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 11.4.2 Anchorage of straight bars: In presence of confinement reinforcement crossing the potential splitting surface shown in Figure 11.5 a) and placed at a net distance $\le ~ 5 \phi$ from the bar to be anchored, or of transverse reinforcement arranged between the bar to be anchored and the free surface (Figure 11.5 b)) or/and of external pressure (Figure 11.5 c)), the design anchorage length may be reduced
  - `evidence_4` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 11.5.2 All types of laps: A design lap length $l _ { \mathrm { s d } }$ between two bars in tension or in compression should be provided, at least equal to the anchorage lengths lbd given in 11.4 multiplied with $k _ { \mathrm { l s } } ,$ , where the clear distance $c _ { s } = c _ { s 1 } + c _ { s 2 }$ to calculate cover <sup>c</sup> should be taken according to Figure 11.10.
  - `evidence_5` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 11.5.2 All types of laps: In case the clear distance exceeds the smaller of 50 mm or $4 \phi _ { \scriptscriptstyle 1 }$ , the design lap length shall be increased by the centre to centre distance of the lapped bars and adequate transverse reinforcement provided to resist the associated transverse forces developed.
  - `evidence_6` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 11.5.2 All types of laps: Where tension laps are located across plastic hinge locations, tension lap length may be designed for $\sigma _ { \mathrm { s d } }$ if:

— a confinement reinforcement is arranged according to 11.5.2(8); or

if the laps are staggered so that the area of lapped bars i $s \leq 3 5 \%$ of the total cross section area of the reinforcement in linear members (beams and columns) $0 \Gamma \leq 5 0 \%$ in planar members (slabs, walls and shells). If staggering of laps is chosen as an option, the distance between adjacent laps should be at least $0 { , } 3 l _ { \mathrm { s d } }$ (see Figure 11.11b)).
- [ ] 人工确认最小充分证据集

## Q20: 什么情况下需要考虑二阶效应？
- status: needs_human_review
- reference_answer: 需要考虑二阶效应的核心判断是：结构变形后的几何效应会显著增大作用效应或显著改变结构行为时，应考虑；对混凝土结构，若其可能显著影响整体稳定性，或影响关键截面达到承载能力极限状态，也应计入二阶效应。
- `claim_1` [supported]: 对钢结构，变形后的几何效应若会显著增大作用效应，或显著改变结构行为，应考虑二阶效应。
  evidence: evidence_1
- `claim_2` [supported]: 对混凝土结构，当二阶效应可能显著影响结构整体稳定性，或影响关键截面达到承载能力极限状态时，应计入二阶效应。
  evidence: evidence_2
  - `evidence_1` EN1993-1-1_2005/EN1993-1-1_2005.md / 5.2.1 Effects of deformed geometry of the structure: (2) The effects of the deformed geometry (second-order effects) should be considered if they increase the action effects significantly or modify significantly the structural behaviour.
  - `evidence_2` EN1992-1-1_2004/EN1992-1-1_2004.md / 5.1.4 Second order effects: (1)P Second order effects (see EN 1990 Section 1) shall be taken into account where they are likely to affect the overall stability of a structure significantly and for the attainment of the ultimate limit state at critical sections.
- [ ] 人工确认最小充分证据集

## Q21: 受弯构件正截面承载力计算的一般步骤是什么？
- status: needs_human_review
- reference_answer: 受弯构件正截面承载力计算可按以下一般流程进行：以控制截面的 ULS 设计弯矩 MEd 作为作用效应；按极限状态截面分析假定建立应变和材料应力关系，即采用平截面假定、忽略混凝土抗拉强度，并采用混凝土和钢筋的设计应力—应变关系；随后建立混凝土压缩合力 Fc 与钢筋拉力 Fs 的平衡，求内力臂 z 和抗弯承载力 MRd，最后以 MEd 与 MRd 的平衡关系完成验算。
- `claim_1` [supported]: 以控制截面的 ULS 设计弯矩 MEd 作为正截面抗弯计算的作用效应。
  evidence: evidence_1
- `claim_2` [supported]: 按极限状态截面分析假定建立应变与材料应力关系：平截面保持平面，忽略混凝土抗拉强度，并采用混凝土和钢筋的设计应力—应变关系。
  evidence: evidence_2
- `claim_3` [supported]: 建立混凝土压缩合力 Fc 与钢筋拉力 Fs 的平衡，求内力臂 z 和抗弯承载力；验算时令设计弯矩 MEd 由抗力矩 MRd 平衡。
  evidence: evidence_3
  - `evidence_1` 1110_WS_EC2_-/1110_WS_EC2_-.md / 3.2.1.2 Determination of the bending reinforcement in general: For equilibrium, the ULS design moment $M _ { E d }$ has to be balanced by the resisting moment $M _ { R d }$ so that:
  - `evidence_2` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.1 Bending with or without axial force: (2)P When determining the ultimate moment resistance of reinforced or prestressed concrete cross-sections, the following assumptions are made:

\- plane sections remain plane.

\- the strain in bonded reinforcement or bonded prestressing tendons, whether in tension or in compression, is the same as that in the surrounding concrete.

\- the tensile strength of the concrete is ignored.

\- the stresses in the concrete in compression are derived from the design stress/strain relationship given in 3.1.7.

\- the stresses in the reinforcing or prestressing steel are derived from the design curves in 3.2 (Figure 3.8) and 3.3 (Figure 3.10).
  - `evidence_3` 1110_WS_EC2_-/1110_WS_EC2_-.md / 3.2.1.2 Determination of the bending reinforcement in general: Bending of the section (according to Figure 3.2.6) will induce a resultant tensile force $F _ { s }$ in the reinforcing steel, and a resultant compressive force in the concrete $F _ { c }$ which acts through the centroid of the effective compressed area .

For equilibrium, the ULS design moment $M _ { E d }$ has to be balanced by the resisting moment $M _ { R d }$ so that:

$$
M _ { E d } = F _ { c } z = F _ { s } z \ ( 3 . 3 )
$$

where z is the lever arm between the resultant forces $F _ { c }$ and $F _ { s }$
- [ ] 人工确认最小充分证据集

## Q22: 后张法预应力损失如何计算
- status: needs_human_review
- reference_answer: 后张法按“张拉端最大应力减损失”计算：在位置 x、时刻 t，以张拉端最大应力扣除即时损失和长期损失，全部损失按绝对值取值。即时损失包括摩擦、锚具就位和混凝土瞬时变形。摩擦损失采用 Δσp,μ(x)=σp,max[1−exp(−μ(αμ+kμx))]；αμ 为长度 x 内的角偏差绝对值和，μ 为摩擦系数，kμ 为无意角偏差。锚具就位量按后张体系技术文件取值；混凝土瞬时变形损失须结合张拉程序考虑。长期损失计入准永久荷载下混凝土徐变、收缩及预应力钢材松弛，松弛与徐变收缩相互作用通常可将松弛应力乘以 0.8 近似处理。长期损失计算中，粘结筋采用局部应力，无粘结筋采用平均应力；内部无粘结筋的平均值沿全长取值。
- `claim_1` [supported]: 在距张拉端 x、时刻 t，后张预应力筋平均预应力按张拉端施加的最大应力扣除即时损失和随时间发展的损失确定，所有损失按绝对值取值。
  evidence: evidence_1
- `claim_2` [supported]: 后张法的即时损失应包括张拉过程中的孔道或偏转装置摩擦损失、锚具就位损失，以及预应力传递给混凝土时混凝土瞬时变形造成的损失。
  evidence: evidence_2
- `claim_3` [supported]: 摩擦损失按 Δσp,μ(x)=σp,max[1−exp(−μ(αμ+kμx))] 估算；αμ 为长度 x 内角偏差绝对值之和，μ 为摩擦系数，kμ 为无意角偏差，x 自最大张拉应力点沿预应力筋量取。
  evidence: evidence_3
- `claim_4` [supported]: 锚固张拉后的锚具就位损失应予考虑，锚具就位量取自后张体系的技术文件。
  evidence: evidence_4
- `claim_5` [supported]: 应结合预应力筋的张拉程序，考虑与混凝土变形相对应的预应力筋应力损失。
  evidence: evidence_5
- `claim_6` [supported]: 长期损失应考虑准永久荷载下混凝土徐变、收缩导致的应变减小，以及受拉预应力钢材松弛导致的应力减小；两者相互作用可近似通过对松弛应力取 0.8 折减系数考虑。
  evidence: evidence_6
- `claim_7` [supported]: 长期损失公式对粘结预应力筋采用局部应力值，对无粘结预应力筋采用平均应力值；内部无粘结筋的平均值沿全长计算。
  evidence: evidence_7
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 7.6.2 Prestressing force: (1) At a given time t and distance x (or arc length) from the active end of the tendon the mean prestress stress $\sigma _ { \mathrm { p , m } } ( x , t )$ should be taken equal to the maximum stress $\sigma _ { \mathrm { p , m a x } }$ imposed at the active end. minus the immediate losses (see 7.6.3) and the time dependent losses (see 7.6.4), using absolute values for all losses.
  - `evidence_2` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 7.6.3.1 General: during the stressing process: losses due to friction between the prestressing steel and duct or deviation devices $\Delta \sigma _ { \mathrm { p , \mu } } ( \mathbf { x } )$ , see 7.6.3.2;

— during the stressing process: losses due to anchorage seating (e.g. wedge draw-in), see 7.6.3.3;

at the transfer of prestress to concrete: losses due to instantaneous deformation of concrete, see 7.6.3.4;
  - `evidence_3` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 7.6.3.2 Losses due to friction: (1) The losses due to friction $\Delta \sigma _ { \mathrm { p , \mu } } \left( x \right)$ in prestressing tendons should be estimated from:

$$
\Delta \sigma _ { \mathrm { p , \mu } } ( x ) = \sigma _ { \mathrm { p , m a x } } \left[ 1 - \exp \left( - \mu { \left( \alpha _ { \mu } + k _ { \mu } x \right) \right) } \right]\tag{7.34}
$$

where

$\alpha _ { \mu }$ is the sum of the absolute values of angular deviations in radians over a distance <sup>x</sup>;

$\mu$ is the coefficient of friction between the tendon and its duct or deviation device;

$k _ { \mu }$ is an unintentional angular deviation for internal post-tensioning tendons in grouted ducts and greased strands in radian per unit length- (curvature); and

x is the distance along the tendon from the point where the prestressing stress is equal to $\sigma _ { \mathrm { p , m a x } }$ (the force at the active end during tensioning).
  - `evidence_4` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 7.6.3.3 Losses due to anchorage seating: (1) Account should be taken of the losses due to anchorage seating, during the operation of anchoring the prestressing steel after tensioning.

NOTE Values for anchorage seating are given in the technical documentation of post-tensioning system.
  - `evidence_5` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 7.6.3.4 Losses due to the instantaneous deformation of concrete: (1) Where relevant, account should be taken of the loss in tendon stress corresponding to the deformation of concrete, considering the tensioning programme in which the tendons are stressed.
  - `evidence_6` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 7.6.4 Time dependent losses of prestress: (1) The time dependent losses should be calculated by considering the following two reductions of stress:

a) That due to the reduction of strain, caused by the deformation of concrete due to creep and shrinkage, under the quasi-permanent loads; and

b) that due to the reduction of stress in the steel due to the relaxation under tension (see B.9).

The interaction between the relaxation of prestressing steel and the concrete deformation due to creep and shrinkage may generally and approximately be considered by applying a reduction factor of 0,8 on the stress relaxation.
  - `evidence_7` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 7.6.4 Time dependent losses of prestress: (3)Formula (7.35) applies to bonded tendons when local values of stresses are used and to unbonded tendons when mean values of stresses are used. The mean values should be calculated between straight sections limited by the deviation points for external tendons or along the entire length in case of internal tendons.
- [ ] 人工确认最小充分证据集

## Q23: 预应力在各类极限状态下的影响是什么
- status: needs_human_review
- reference_answer: 预应力可按作用或抗力处理，通常应作为荷载工况的一部分纳入作用组合以及内力矩和轴力。在 ULS 中，预应力设计值可基于平均预应力确定；对永久无粘结筋还应考虑全构件变形对预应力钢筋应力增长的影响。在 SLS 和疲劳验算中，应计及预应力的可能变动，并采用由平均预应力估算的上下特征值。偶然与地震设计状况的作用组合也均包含预应力 P。
- `claim_1` [supported]: 预应力效应可作为由预应变和预曲率引起的作用或抗力处理；通常应作为荷载工况的一部分纳入 EN 1990 的作用组合，并计入施加的内力矩和轴力。
  evidence: evidence_1
- `claim_2` [supported]: 在承载能力极限状态（ULS）中，预应力设计值可由平均预应力乘以系数确定；对永久无粘结筋构件，计算预应力钢筋应力增长时通常需要考虑整个构件的变形。
  evidence: evidence_2
- `claim_3` [supported]: 在正常使用极限状态和疲劳计算中，应考虑预应力的可能变动，并由平均预应力估算上、下两个特征预应力值。
  evidence: evidence_3
- `claim_4` [supported]: 在偶然和地震设计状况的作用效应组合中，预应力 P 均被明确纳入。
  evidence: evidence_4, evidence_5
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 5.10.1 General: (2) The effects of prestressing may be considered as an action or a resistance caused by prestrain and precurvature. The bearing capacity should be calculated accordingly.

(3) In general prestress is introduced in the action combinations defined in EN 1990 as part of the loading cases and its effects should be included in the applied internal moment and axial force.
  - `evidence_2` EN1992-1-1_2004/EN1992-1-1_2004.md / 5.10.8 Effects of prestressing at ultimate limit state: (1) In general the design value of the prestressing force may be determined by $P _ { \mathrm { d , t } } ( \mathsf { x } ) =$ $\varkappa _ { \sf P } , P _ { \sf m , t } ( \sf x )$ (see 5.10.3 (4) for the definition of $P _ { \mathrm { m , t } } ( \mathsf { x } ) )$ and 2.4.2.2 for $\gamma _ { \mathsf { p } }$

(2) For prestressed members with permanently unbonded tendons, it is generally necessary to take the deformation of the whole member into account when calculating the increase of the stress in the prestressing steel.
  - `evidence_3` EN1992-1-1_2004/EN1992-1-1_2004.md / 5.10.9 Effects of prestressing at serviceability limit state and limit state of fatigue: $( 1 ) \mathsf { P }$ For serviceability and fatigue calculations allowance shall be made for possible variations in prestress. Two characteristic values of the prestressing force at the serviceability limit state are estimated from:

$$
P _ { \mathrm { k , s u p } } = r _ { \mathrm { s u p } } P _ { \mathrm { m , t } } \left( x \right)\tag{5.47}
$$

$$
P _ { \mathrm { k , i n f } } = r _ { \mathrm { i n f } } P _ { \mathrm { m , t } } ( \mathsf { x } )\tag{5.48}
$$
  - `evidence_4` EN1990_2002/EN1990_2002.md / 6.4.3.3 Combinations of actions for accidental design situations: (1) The general format of effects of actions should be :

$$
E _ { d } = E \Big \{ G _ { k , j } ; P ; A _ { d } ; ( \psi _ { 1 , 1 } \mathrm { o r } \psi _ { 2 , 1 } ) Q _ { k , 1 } ; \psi _ { 2 , i } Q _ { k , i } \Big \} \quad j \geq 1 ; i > 1\tag{6.11a}
$$
  - `evidence_5` EN1990_2002/EN1990_2002.md / 6.4.3.4 Combinations of actions for seismic design situations: (1) The general format of effects of actions should be :

$$
E _ { d } = E \Big \{ G _ { k , j } ; P ; A _ { E d } ; \psi _ { 2 , i } Q _ { k , i } \Big \} \quad j \geq 1 ; i \geq 1\tag{6.12a}
$$
- [ ] 人工确认最小充分证据集

## Q24: 剪应力一般验证程序是怎样的
- status: needs_human_review
- reference_answer: 剪力一般验算程序为：先确定无剪力钢筋抗剪承载力 V_Rd,c、剪力钢筋贡献 V_Rd,s 和最大抗剪承载力 V_Rd,max；在各截面比较 V_Ed 与 V_Rd,c。若 V_Ed≤V_Rd,c，无需按计算配置剪力钢筋，但通常仍应满足最小剪力钢筋要求（规定情形可省略）。若 V_Ed>V_Rd,c，则配置足够剪力钢筋使 V_Ed≤V_Rd，并在全构件验算相应剪力不超过 V_Rd,max；同时验算纵向受拉钢筋承受剪力产生的附加拉力。
- `claim_1` [supported]: 一般剪力验算先采用构件无剪力钢筋时的设计抗剪承载力 V_Rd,c、由屈服剪力钢筋承担的 V_Rd,s，以及受压斜杆压碎所限制的最大承载力 V_Rd,max。
  evidence: evidence_1
- `claim_2` [supported]: 对所考察截面，若设计剪力 V_Ed 不大于 V_Rd,c，则无需按计算配置剪力钢筋。
  evidence: evidence_2
- `claim_3` [supported]: 即使计算不需要剪力钢筋，通常仍应按第 9.2.2 条设置最小剪力钢筋；能横向重分配荷载的板类构件或不重要构件可省略。
  evidence: evidence_3
- `claim_4` [supported]: 若 V_Ed 大于 V_Rd,c，应配置足够剪力钢筋使 V_Ed 不大于 V_Rd；同时，扣除翼缘贡献后的设计剪力不得在构件任何位置超过 V_Rd,max。
  evidence: evidence_4
- `claim_5` [supported]: 还应验算纵向受拉钢筋能承受剪力引起的附加拉力。
  evidence: evidence_5
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.2.1 General verification procedure: $V _ { \sf R d , c }$ is the design shear resistance of the member without shear reinforcement.

$V _ { \sf R d , s }$ is the design value of the shear force which can be sustained by the yielding shear reinforcement.

$V _ { \sf R d , m a x }$ is the design value of the maximum shear force which can be sustained by the member, limited by crushing of the compression struts.
  - `evidence_2` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.2.1 General verification procedure: (3) In regions of the member where $V _ { \sf E d } \leq V _ { \sf R d , c }$ no calculated shear reinforcement is necessary. $V _ { \mathsf { E d } }$ is the design shear force in the section considered resulting from external loading and prestressing (bonded or unbonded).
  - `evidence_3` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.2.1 General verification procedure: (4) When, on the basis of the design shear calculation, no shear reinforcement is required, minimum shear reinforcement should nevertheless be provided according to 9.2.2. The minimum shear reinforcement may be omitted in members such as slabs (solid, ribbed or hollow core slabs) where transverse redistribution of loads is possible.
  - `evidence_4` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.2.1 General verification procedure: (5) In regions where $V _ { \sf E d } > V _ { \sf R d , c }$ according to Expression (6.2), sufficient shear reinforcement should be provided in order that $V _ { \sf E d } \leq V _ { \sf R d }$ (see Expression (6.8)).

(6) The sum of the design shear force and the contributions of the flanges, $V _ { \mathsf { E d } } - V _ { \mathsf { c c d } } - V _ { \mathsf { t d } }$ should not exceed the permitted maximum value $V _ { \sf R d , m a x }$ (see 6.2.3), anywhere in the member.
  - `evidence_5` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.2.1 General verification procedure: (7) The longitudinal tension reinforcement should be able to resist the additional tensile force caused by shear (see 6.2.3 (7)).
- [ ] 人工确认最小充分证据集

## Q25: 单向板的设计步骤包括哪些
- status: review_not_converged
- reference_answer: 单向板可按以下步骤设计：先针对相关SLS和ULS建立结构与荷载模型，并考虑设计工况和荷载工况；先进行SLS控制（板厚通常由挠度限值控制），再进行ULS验算；对满足荷载和跨距条件的连续单向板，可用表列法取得弯矩和剪力，并采用规定的总设计极限荷载；随后按正弯矩配置纵向受拉钢筋，在按单向板受力的区域配置次要钢筋；如需设置抗剪钢筋，则按梁的构造要求处理。
- `claim_1` [supported]: 单向板设计首先应针对相关的承载能力极限状态和正常使用极限状态建立结构与荷载模型，并考虑相应设计工况和荷载工况。
  evidence: evidence_1
- `claim_2` [supported]: 设计应先满足正常使用极限状态（SLS），再满足承载能力极限状态（ULS）；板厚通常受挠度限值控制。
  evidence: evidence_2
- `claim_3` [supported]: 对于满足规定荷载与跨距条件的连续单向板，可用表3.3取得弯矩和剪力；该表中的总设计极限荷载为1.35Gk加1.50Qk。
  evidence: evidence_3, evidence_4
- `claim_4` [supported]: 应按所需正弯矩配置纵向受拉钢筋，并在按单向板受力的区域配置次要钢筋；若设置抗剪钢筋，其构造应按梁执行。
  evidence: evidence_5, evidence_6
  - `evidence_1` DG_EN1990/DG_EN1990.md / 3.5. Limit state design: The design procedure using the limit state concept consists of setting up structural and load models for relevant ultimate and serviceability limit states which are considered in the various design situations and load cases
  - `evidence_2` 1110_WS_EC2_-/1110_WS_EC2_-.md / 1.5.1.1 Slenderness: The design of slabs has to fulfil both Serviceability Limit States (SLS) and Ultimate Limit States (ULS) requirements (in this exact order!). In general the height “h” of slabs is controlled by the deflection limits
  - `evidence_3` DG_EN1992-1-1__-1-2/DG_EN1992-1-1__-1-2.md / 3.8.1. One-way spanning slabs and continuous beams: A further approximation may be made if: (1) the characteristic variable load does not exceed the characteristic permanent load; (2) loads are predominantly uniformly distributed over three or more spans; and (3) variations in span lengths do not exceed 15% of the longest span. Under these conditions the bending moments and shear forces may be obtained using Table 3.3.
  - `evidence_4` DG_EN1992-1-1__-1-2/DG_EN1992-1-1__-1-2.md / 3.8.1. One-way spanning slabs and continuous beams: F is the total design ultimate load (1.35Gk + 1.50Qk); 1 is the effective span.
  - `evidence_5` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 12.4.1 General: To ensure a minimum ability to locally redistribute sectional forces transverse to the span direction,secondary reinforcement is to be placed in areas of slabs which can be considered to behave as one-wayslabs.b  These spacing are consistent with the shear model in 8.2.3. Where alternative models are used alternativespacings may be required.C   $A _ { \mathsf { s , r e q \ s p a n } }$ is the required reinforcement for positive bending moments at the span.
  - `evidence_6` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 12.4.2 Shear reinforcement: (4) The shear reinforcement for a one-way slab should be detailed as for a beam, see 12.3.3.
- [ ] 人工确认最小充分证据集

## Q26: 单向板构造配筋有什么规定
- status: needs_human_review
- reference_answer: 单向实心板除主受力钢筋外，应设置不少于主筋20%的次要横向钢筋；但在靠近支座且无横向弯矩处，主负筋横向可不配横向钢筋。钢筋间距不得超过限值：一般区域主筋为3h且不大于400 mm、次要钢筋为3.5h且不大于450 mm；集中荷载区或最大弯矩区分别为主筋2h且不大于250 mm、次要钢筋3h且不大于400 mm。简支板至少一半跨中计算钢筋应伸入支座并锚固。若板边有未计入分析的部分固结，顶筋应按相邻跨最大弯矩至少25%配置，伸出长度不少于相邻跨的0.2倍，并在内支座连续、端支座锚固。
- `claim_1` [supported]: 单向实心板应配置不小于主受力钢筋20%的次要横向钢筋；但靠近支座、且不存在横向弯矩的区域，主负筋横向无需配置横向钢筋。
  evidence: evidence_1
- `claim_2` [supported]: 板内钢筋间距不得超过规定最大值：主筋一般为3h且不大于400 mm，次要钢筋一般为3.5h且不大于450 mm；集中荷载区或最大弯矩区分别收紧为主筋2h且不大于250 mm、次要钢筋3h且不大于400 mm。
  evidence: evidence_2
- `claim_3` [supported]: 简支板至少一半计算跨中钢筋应延伸至支座并按8.4.4锚固。
  evidence: evidence_3
- `claim_4` [supported]: 当板边存在未计入分析的部分固结时，顶面钢筋应能承受相邻跨最大弯矩至少25%，自支座面起延伸至少相邻跨长的0.2倍；内支座处应连续、端支座处应锚固。
  evidence: evidence_4
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 9.3.1.1 General: (2) Secondary transverse reinforcement of not less than 20% of the principal reinforcement should be provided in one way slabs. In areas near supports transverse reinforcement to principal top bars is not necessary where there is no transverse bending moment.
  - `evidence_2` EN1992-1-1_2004/EN1992-1-1_2004.md / 9.3.1.1 General: The recommended value is:

\- for the principal reinforcement, $3 h \leq 4 0 0$ mm, where h is the total depth of the slab;

\- for the secondary reinforcement, $3 , 5 h \le ~ 4 5 0 ~ \mathrm { m m }$

In areas with concentrated loads or areas of maximum moment those provisions become respectively:

\- for the principal reinforcement, $2 h \leq 2 5 0 ~ \mathrm { m m }$

for the secondary reinforcement, 3h ≤ 400 mm.
  - `evidence_3` EN1992-1-1_2004/EN1992-1-1_2004.md / 9.3.1.2 Reinforcement in slabs near supports: (1) In simply supported slabs, half the calculated span reinforcement should continue up to the support and be anchored therein in accordance with 8.4.4.
  - `evidence_4` EN1992-1-1_2004/EN1992-1-1_2004.md / 9.3.1.2 Reinforcement in slabs near supports: (2) Where partial fixity occurs along an edge of a slab, but is not taken into account in the analysis, the top reinforcement should be capable of resisting at least 25% of the maximum moment in the adjacent span. This reinforcement should extend at least 0,2 times the length of the adjacent span, measured from the face of the support. It should be continuous across internal supports and anchored at end supports.
- [ ] 人工确认最小充分证据集

## Q27: 单向板分布筋的配置有什么规定
- status: needs_human_review
- reference_answer: 单向板应设置垂直于主受力钢筋的分布（次要横向）钢筋，面积不少于主受力钢筋的20%。靠近支座且不存在横向弯矩时，主受力上部钢筋可不设横向钢筋。分布筋常规最大间距为3.5h且不超过450 mm；在集中荷载区或最大弯矩区，最大间距为3h且不超过400 mm（h为板总厚度）。
- `claim_1` [supported]: 单向板应配置与主受力筋垂直的次要（分布）钢筋，其面积不应小于主受力钢筋的20%。
  evidence: evidence_1
- `claim_2` [supported]: 靠近支座处，如不存在横向弯矩，则主受力上部钢筋不需要配置横向钢筋。
  evidence: evidence_1
- `claim_3` [supported]: 分布筋的常规最大间距应不超过3.5h且不超过450 mm，其中h为板总厚度。
  evidence: evidence_2
- `claim_4` [supported]: 在集中荷载区或最大弯矩区，分布筋最大间距应不超过3h且不超过400 mm。
  evidence: evidence_3
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 9.3.1.1 General: (2) Secondary transverse reinforcement of not less than 20% of the principal reinforcement should be provided in one way slabs. In areas near supports transverse reinforcement to principal top bars is not necessary where there is no transverse bending moment.
  - `evidence_2` EN1992-1-1_2004/EN1992-1-1_2004.md / 9.3.1.1 General: \- for the secondary reinforcement, $3 , 5 h \le ~ 4 5 0 ~ \mathrm { m m }$
  - `evidence_3` EN1992-1-1_2004/EN1992-1-1_2004.md / 9.3.1.1 General: for the secondary reinforcement, 3h ≤ 400 mm.
- [ ] 人工确认最小充分证据集

## Q28: 构件在哪些情况下无需设计抗剪力钢筋
- status: needs_human_review
- reference_answer: 构件某受剪区域的设计剪应力 τEd 不大于按 8.2.2 和 8.4.3 确定的 τRd,c 时，无需计算配置抗剪钢筋。可是，这不自动免除最小抗剪钢筋要求：线性构件仍可能须按第12章配置；静定结构中 d＞500 mm 的线性构件必须配置最小抗剪钢筋。
- `claim_1` [supported]: 在构件的某一受剪区域，当设计剪应力 τEd 不大于按 8.2.2 和 8.4.3 确定的混凝土抗剪强度 τRd,c 时，无需计算配置抗剪钢筋。
  evidence: evidence_1
- `claim_2` [supported]: 即使按受剪计算无需抗剪钢筋，线性构件仍可能需要按第12章配置最小抗剪钢筋；其中静定结构内 d 大于500 mm的线性构件必须配置最小抗剪钢筋。
  evidence: evidence_1
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.2.1 General verification procedure: b) no calculated shear reinforcement is required in regions of the members where:

τ<sub>Ed</sub> $\leq \tau _ { \mathrm { R d , c } }$ according to 8.2.2 and 8.4.3;

c) otherwise, shear reinforcement shall be designed according to 8.2.3 and 8.4.4:

$$
\leq
$$

(2) When, on the basis of the design shear calculation, no shear reinforcement is required, minimum shear reinforcement may nevertheless be necessary for linear members, according to Clause 12

For linear members in statically determinate structures with <sup>d</sup> $> 5 0 0$ mm, minimum shear reinforcement shall be provided.
- [ ] 人工确认最小充分证据集

## Q29: 需要设计剪力筋的构件有什么特征
- status: needs_human_review
- reference_answer: 需要设计剪力筋的构件（或构件区域）的核心特征是：设计剪力 V_Ed 超过无剪力筋抗剪承载力 V_Rd,c，因此必须配置足够剪力筋，使 V_Ed 不大于 V_Rd。其设计采用桁架模型；对于竖向剪力筋，抗剪承载力取 V_Rd,s 与 V_Rd,max 中的较小值；同时，纵向受拉钢筋须能承受剪力造成的附加拉力。
- `claim_1` [supported]: 需要按设计配置剪力筋的构件区域，其设计剪力作用效应大于无剪力筋构件的设计抗剪承载力，即 V_Ed > V_Rd,c；应配置足够剪力筋，使 V_Ed ≤ V_Rd。
  evidence: evidence_1
- `claim_2` [supported]: 这类构件的剪力设计采用桁架模型；竖向剪力筋时，抗剪承载力取 V_Rd,s 与 V_Rd,max 两者中的较小值。
  evidence: evidence_2, evidence_3
- `claim_3` [supported]: 这类构件的纵向受拉钢筋还应能承受剪力引起的附加拉力。
  evidence: evidence_4
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.2.1 General verification procedure: (5) In regions where $V _ { \sf E d } > V _ { \sf R d , c }$ according to Expression (6.2), sufficient shear reinforcement should be provided in order that $V _ { \sf E d } \leq V _ { \sf R d }$ (see Expression (6.8)).
  - `evidence_2` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.2.3 Members requiring design shear reinforcement: (1) The design of members with shear reinforcement is based on a truss model (Figure 6.5).
  - `evidence_3` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.2.3 Members requiring design shear reinforcement: (3) For members with vertical shear reinforcement, the shear resistance, $V _ { \mathrm { R d } }$ is the smaller value of:
  - `evidence_4` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.2.1 General verification procedure: (7) The longitudinal tension reinforcement should be able to resist the additional tensile force caused by shear (see 6.2.3 (7)).
- [ ] 人工确认最小充分证据集

## Q30: 结构抗扭转设计程序是怎样的
- status: review_not_converged
- reference_answer: 结构抗扭设计可按以下程序进行：先使设计与分析模型的扭转刚度假定一致；若分析忽略扭转刚度，通常可在承载能力极限状态忽略相应扭矩，但仍配置最小箍筋和纵筋以控制开裂。然后按截面类型判断是否考虑翘曲扭转：闭口薄壁和实体截面通常可忽略，开口薄壁构件则可能需要考虑，并按弯曲、纵向轴力和剪力规则设计。对符合条件的单室薄壁截面或子截面，按公式（8.81）确定抗扭能力。扭转与弯矩、剪力、轴力组合时，可采用逐壁元程序，或采用8.3.6的简化线性相互作用验算，利用率之和不大于1.0。最后按扭转是否为静力平衡所必需确定配筋：必需时抗扭钢筋包围整个截面；仅协调扭转时按Table 12.1（NDP）配置最小抗扭钢筋。
- `claim_1` [supported]: 抗扭设计应与分析所采用的刚度假定一致；若分析中忽略扭转刚度，通常可在承载能力极限状态忽略相应扭矩，但应配置最小箍筋和纵筋以防止过度开裂。
  evidence: evidence_1
- `claim_2` [supported]: 闭口薄壁及实体截面通常可忽略翘曲扭转；开口薄壁构件则可能需要考虑翘曲扭转，并按弯曲、纵向轴力和剪力规则设计截面各部分。
  evidence: evidence_2
- `claim_3` [supported]: 对单室薄壁截面或等效壁厚恒定的子截面，设计抗扭能力按公式（8.81）取三个规定抗扭应力抗力中的最小值。
  evidence: evidence_3
- `claim_4` [supported]: 扭转与弯矩、剪力和轴力组合时，可选择逐个壁元的设计程序，或采用8.3.6所述基于相互作用公式的简化程序。
  evidence: evidence_4
- `claim_5` [supported]: 简化的组合内力截面抗力验算采用线性准则；各内力设计作用与相应设计抗力之比的求和不应大于1.0。
  evidence: evidence_5
- `claim_6` [supported]: 若结构静力平衡依赖构件抗扭能力，抗扭钢筋应包围整个截面；若扭转仅由协调产生且平衡不依赖抗扭能力，则按Table 12.1（NDP）配置最小抗扭钢筋。
  evidence: evidence_6
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.3.1 General considerations for torsion: (1) Where a specific stiffness has been considered in the analysis according to 7.1(6), the corresponding internal forces shall be considered in design. If a specific stiffness was neglected in the analysis, e.g. torsional stiffness, then normally the corresponding internal forces, e.g. torque, may be neglected at the ultimate limit state. In such cases, a minimum reinforcement, given in 12.2, 12.3 and 12.6, in the form of stirrups and longitudinal bars should be provided in order to prevent excessive cracking.
  - `evidence_2` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.3.2 Internal forces due to torsion in compact or closed sections; 8.3.3 Internal forces due to torsion in open sections: (1) In open thin walled members it may be necessary to consider warping torsion. In this case the different parts of the section should be designed according to the rules for bending and longitudinal axial force in 8.1 and shear in 8.2.
  - `evidence_3` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.3.4 Torsional resistance of compact or closed sections: (1) For a single cell, thin-walled section or a sub-section with constant effective wall thickness $t _ { \mathrm { e f f } } ,$ the design torsional capacity may be calculated as:
  - `evidence_4` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.3.5 Design procedure for combination of actions: (1) Design for combined action of torsion, bending, shear and axial forces may follow:
  - `evidence_5` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 8.3.6 Interaction formula: (1) A simplified and conservative verification of the resistance of cross-sections subjected to combination of internal forces may be performed based on the following linear criterion:
  - `evidence_6` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 12.3.3 Shear and torsion reinforcement: (7) When static equilibrium assumed in the analysis depends on the torsional resistance of elements of a structure, the torsion reinforcement shall comply with the rules given in (8) and Figure 12.3 and shall enclose the whole section. When torsion arises only from compatibility and the structure is not dependent on torsional resistance for its equilibrium, minimum torsional reinforcement shall be provided according to Table 12.1 (NDP)
- [DISPUTED] `claim_2`: quote 仅含 8.3.3(1) 开口薄壁部分（4894行）；claim 前半『闭口薄壁及实体截面通常可忽略翘曲扭转』来自 8.3.2(1)（4850行），该句不在 quote 中。section 字段虽列 8.3.2 与 8.3.3，但引文只覆盖一半，证据不足。
- [DISPUTED] `claim_3`: quote 仅引言『may be calculated as:』（4898行）；claim 所指公式(8.81)取三个抗扭应力抗力最小值是 4901 行 min{}，不在 quote 中，引文未直接支持具体公式内容。
- [DISPUTED] `claim_4`: quote 仅『may follow:』（4966行）引言；claim 所述逐壁元程序与 8.3.6 简化程序在 4968–4970 行，不在 quote 中，引文不含任一选项内容。
- [DISPUTED] `claim_5`: quote 仅『based on the following linear criterion:』（4978行）引言；claim 的『利用率之和不大于1.0』是 4981 行公式(8.86) Σ(S_Ed/S_Rd)≤1,0，不在 quote 中。
- [ ] 人工确认最小充分证据集

## Q31: 其他通用问题：
- status: needs_human_review
- reference_answer: 语料不足以回答：题目未提供具体问题，无法生成针对性的 Eurocode 参考答案。
- `claim_1` [corpus_gap]: 题目仅给出“其他通用问题：”，未包含任何具体的技术问题或待判断事项；因此无法从已完整检索的语料中形成针对性的、可证据支持的回答。
  evidence: (none)
- [ ] 人工确认最小充分证据集
