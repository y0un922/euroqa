# Gold 最小充分证据集人工复核 (20260714_053706)

范围：全部题目。只有人工确认后该题才可进入正式 CRec。

## Q01: 请给出混凝土结构设计中相关作用荷载和材料的分项系数。
- status: needs_human_review
- reference_answer: 按 EN 1990:2002 的 EQU（Set A）推荐值，在持久和短暂设计情况下：不利永久作用 γ_Gj,sup=1.10，有利永久作用 γ_Gj,inf=0.90，不利主导可变作用 γ_Q,1=1.50，不利伴随可变作用 γ_Q,i=1.50。偶然和地震设计情况下的承载能力极限状态作用分项系数为 1.0；正常使用极限状态的作用分项系数为 1.0，除非 EN 1991 至 EN 1999 另有规定。按 EN 1992-1-1:2004：持久和短暂设计情况下，γc=1.5、γs=1.15、γys=1.15；偶然设计情况下，γc=1.2、γs=1.0、γys=1.0。
- `c01` [supported]: 在持久和短暂设计情况下，EQU（Set A）推荐的不利永久作用分项系数 γ_Gj,sup 为 1.10。
  evidence: ev01
- `c02` [supported]: 在持久和短暂设计情况下，EQU（Set A）推荐的有利永久作用分项系数 γ_Gj,inf 为 0.90。
  evidence: ev01
- `c03` [supported]: 在持久和短暂设计情况下，EQU（Set A）推荐的不利主导可变作用分项系数 γ_Q,1 为 1.50。
  evidence: ev01
- `c04` [supported]: 在持久和短暂设计情况下，EQU（Set A）推荐的不利伴随可变作用分项系数 γ_Q,i 为 1.50。
  evidence: ev01
- `c05` [supported]: 偶然和地震设计情况下的承载能力极限状态，作用分项系数应取 1.0。
  evidence: ev02
- `c06` [supported]: 正常使用极限状态的作用分项系数应取 1.0，除非 EN 1991 至 EN 1999 另有规定。
  evidence: ev03
- `c07` [supported]: 持久和短暂设计情况下，混凝土材料分项系数 γc 为 1.5。
  evidence: ev04
- `c08` [supported]: 持久和短暂设计情况下，普通钢筋材料分项系数 γs 为 1.15。
  evidence: ev04
- `c09` [supported]: 持久和短暂设计情况下，预应力钢材材料分项系数 γys 为 1.15。
  evidence: ev04
- `c10` [supported]: 偶然设计情况下，混凝土材料分项系数 γc 为 1.2。
  evidence: ev04
- `c11` [supported]: 偶然设计情况下，普通钢筋材料分项系数 γs 为 1.0。
  evidence: ev04
- `c12` [supported]: 偶然设计情况下，预应力钢材材料分项系数 γys 为 1.0。
  evidence: ev04
  - `ev01` EN1990_2002/EN1990_2002.md / EN 1990:2002 (E): (*) Variable actions are those considered in Table A1.1 NOTE 1 The γ values may be set by the National annex. The recommended set of values for γ are :  $\gamma _ { \mathrm { G j , s u p } } = 1 , 1 0$   $\gamma _ { \mathrm { G j , i n f } } = 0 { , } 9 0$   $\gamma _ { \mathrm { Q , 1 } } = 1 \mathrm { , } 5 0$  where unfavourable (0 where favourable)  $\gamma _ { \mathrm { Q , i } } = 1 , 5 0$  where unfavourable (0 where favourable)
  - `ev02` EN1990_2002/EN1990_2002.md / A1.3.2 Design values of actions in the accidental and seismic design situations: (1) The partial factors for actions for the ultimate limit states in the accidental and seismic design situations (expressions 6.11a to 6.12b) should be 1,0. - values are given in Table A1.1.
  - `ev03` EN1990_2002/EN1990_2002.md / A1.4.1 Partial factors for actions: (1) For serviceability limit states the partial factors for actions should be taken as 1,0 except if differently specified in EN 1991 to EN 1999.
  - `ev04` EN1992-1-1_2004/EN1992-1-1_2004.md / 2.4.2.4 Partial factors for materials: <table><tr><td rowspan=1 colspan=1>Design situations</td><td rowspan=1 colspan=1>Yc for concrete</td><td rowspan=1 colspan=1>Ys for reinforcing steel</td><td rowspan=1 colspan=1>Yys for prestressing steel</td></tr><tr><td rowspan=1 colspan=1>Persistent&amp;Transient</td><td rowspan=1 colspan=1>1.5</td><td rowspan=1 colspan=1>1,15</td><td rowspan=1 colspan=1>1,15</td></tr><tr><td rowspan=1 colspan=1>Accidental</td><td rowspan=1 colspan=1>1,2</td><td rowspan=1 colspan=1>1,0</td><td rowspan=1 colspan=1>1.0</td></tr></table>
- [ ] 人工确认最小充分证据集

## Q02: 请给出混凝土材料的强度与变形的相关定义、相互关系及如何计算。
- status: needs_human_review
- reference_answer: 混凝土强度等级与特征（5%）圆柱体抗压强度 fck 或立方体强度有关；抗拉强度是同心拉伸下的最高应力，若已知劈裂抗拉强度，可近似按 fct=0.9fct,sp 换算。龄期抗压强度可按 fcm(t)=βcc(t)fcm 估算，进而按 Ecm(t)=[fcm(t)/fcm]^0.3Ecm 计算龄期弹性模量；对石英岩骨料混凝土，Ecm 是从 0 到 0.4fcm 的割线模量。徐变和收缩均受湿度、构件尺寸与混凝土组成影响，徐变还与加载龄期、持续时间和荷载大小有关；恒定压应力下的最终徐变应变为 εcc(∞,t0)=φ(∞,t0)(σc/Ec)。总收缩应变为 εcs=εcd+εca，其中干燥收缩按 εcd(t)=βds(t,ts)khεcd,0 计算，自生收缩按 εca(t)=βas(t)εca(∞) 计算，且 εca(∞)=2.5(fck−10)10^-6。短期单轴受压的非线性应力—应变关系可采用 σc/fcm=(kη−η²)/[1+(k−2)η]。
- `c1` [supported]: 混凝土抗压强度等级与特征（5%）圆柱体强度 fck 或立方体强度有关。
  evidence: e1
- `c2` [supported]: 抗拉强度定义为同心拉伸加载下达到的最高应力。
  evidence: e2
- `c3` [supported]: 当以劈裂抗拉强度 fct,sp 确定时，轴心抗拉强度可近似取 fct = 0.9 fct,sp。
  evidence: e3
- `c4` [supported]: 龄期 t 的平均抗压强度按 fcm(t)=βcc(t)fcm 估算，其中 βcc(t) 随龄期及水泥类型参数 s 变化。
  evidence: e4
- `c5` [supported]: 对石英岩骨料混凝土，弹性模量 Ecm 为应力从 0 到 0.4fcm 的割线模量。
  evidence: e5
- `c6` [supported]: 龄期 t 的弹性模量可按 Ecm(t)=[fcm(t)/fcm]^0.3 Ecm 估算。
  evidence: e6
- `c7` [supported]: 混凝土徐变和收缩受环境湿度、构件尺寸和混凝土组成影响；徐变还受首次加载时的成熟度、荷载持续时间和荷载大小影响。
  evidence: e7
- `c8` [supported]: 恒定压应力 σc 在混凝土龄期 t0 施加时，最终徐变变形按 εcc(∞,t0)=φ(∞,t0)(σc/Ec) 计算。
  evidence: e8
- `c9` [supported]: 总收缩应变由干燥收缩应变和自生收缩应变组成，即 εcs=εcd+εca。
  evidence: e9
- `c10` [supported]: 龄期 t 的干燥收缩应变按 εcd(t)=βds(t,ts)khεcd,0 计算。
  evidence: e10
- `c11` [supported]: 自生收缩应变按 εca(t)=βas(t)εca(∞) 计算，其最终值为 εca(∞)=2.5(fck−10)10^-6。
  evidence: e11
- `c12` [supported]: 短期单轴受压的非线性分析可用归一化应力—应变关系 σc/fcm=(kη−η²)/[1+(k−2)η] 表示。
  evidence: e12
  - `e1` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.2 Strength: (1)P The compressive strength of concrete is denoted by concrete strength classes which relate to the characteristic (5%) cylinder strength $\pmb { f } _ { \mathtt { C k } } ,$ , or the cube strength $f _ { \mathtt { C K , C u b e } }$ , in accordance with EN 206-1.
  - `e2` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.2 Strength: (7)P The tensile strength refers to the highest stress reached under concentric tensile loading.
For the flexural tensile strength reference should be made to 3.1.8 (1).
  - `e3` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.2 Strength: (8) Where the tensile strength is determined as the splitting tensile strength, $f _ { \mathrm { c t , s p } }$ , an approximate value of the axial tensile strength, fct, may be taken as:

$$
f _ { \mathrm { c t } } = 0 , 9 f _ { \mathrm { c t , s p } }\tag{3.3}
$$
  - `e4` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.2 Strength: (6) The compressive strength of concrete at an age t depends on the type of cement,

temperature and curing conditions. For a mean temperature of $\scriptstyle 2 0 ^ { \circ } \complement$ and curing in accordance with EN 12390 the compressive strength of concrete at various ages $\pmb { f } _ { \mathsf { c m } } ( t )$ may be estimated from Expressions (3.1) and (3.2).

$$
\begin{array} { r } { f _ { \mathrm { c m } } ( t ) = \beta _ { \mathrm { c c } } ( t ) \ f _ { \mathrm { c m } } } \end{array}\tag{3.1}
$$

with

$$
\beta _ { c c } ( t ) = \mathbf { e } \times \mathbf { p } \left\{ \pmb { s } \left[ 1 - \left( \frac { 2 8 } { t } \right) ^ { 1 / 2 } \right] \right\}\tag{3.2}
$$
  - `e5` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.3 Elastic deformation: (2) The modulus of elasticity of a concrete is controlled by the moduli of elasticity of its components. Approximate values for the modulus of elasticity $E _ { \mathrm { { c m } } } ,$ secant value between $\sigma _ { \mathrm { c } } = 0$ and $0 , 4 f _ { \mathrm { c m } } ,$ for concretes with quartzite aggregates, are given in Table 3.1.
  - `e6` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.3 Elastic deformation: $$
E _ { \mathrm { c m } } ( t ) = \left( f _ { \mathrm { c m } } ( t ) / f _ { \mathrm { c m } } \right) ^ { 0 , 3 } E _ { \mathrm { c m } }\tag{3.5}
$$

where $E _ { \mathrm { { c m } } } ( t )$ and $\pmb { f } _ { \mathsf { c m } } ( t )$ are the values at an age of t days and $E _ { \mathsf { c m } }$ and $\pmb { f _ { \mathrm { c m } } }$ are the values determined at an age of 28 days.
  - `e7` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.4 Creep and shrinkage: (1)P Creep and shrinkage of the concrete depend on the ambient humidity, the dimensions of the element and the composition of the concrete. Creep is also influenced by the maturity of the concrete when the load is first applied and depends on the duration and magnitude of the loading.
  - `e8` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.4 Creep and shrinkage: (3) The creep deformation of concrete $\varepsilon _ { \tt c c } ( \infty , t _ { 0 } )$ at time $t = \infty$ for a constant compressive stress $\sigma _ { \mathsf { C } }$ applied at the concrete age $t _ { 0 } ,$ , is given by:

$$
\varepsilon _ { \mathrm { c c } } ( \infty , t _ { 0 } ) = \varphi ( \infty , t _ { 0 } ) . ( \sigma _ { \mathrm { c } } / E _ { \mathrm { c } } )\tag{3.6}
$$
  - `e9` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.4 Creep and shrinkage: (6) The total shrinkage strain is composed of two components, the drying shrinkage strain and the autogenous shrinkage strain. The drying shrinkage strain develops slowly, since it is a function of the migration of the water through the hardened concrete. The autogenous shrinkage strain develops during hardening of the concrete: the major part therefore develops in the early days after casting. Autogenous shrinkage is a linear function of the concrete strength. It should be considered specifically when new concrete is cast against hardened concrete. Hence the values of the total shrinkage strain $\scriptstyle { \varepsilon _ { \mathsf { C S } } }$ follow from

$$
\varepsilon _ { \tt c s } = \varepsilon _ { \tt c d } + \varepsilon _ { \tt c a }\tag{3.8}
$$
  - `e10` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.4 Creep and shrinkage: The development of the drying shrinkage strain in time follows from:

$$
\varepsilon _ { \mathrm { c d } } ( t ) = \beta _ { \mathrm { d s } } ( t , t _ { \mathrm { s } } ) \cdot k _ { \mathrm { h } } \cdot \varepsilon _ { \mathrm { c d , 0 } }\tag{3.9}
$$
  - `e11` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.4 Creep and shrinkage: The autogenous shrinkage strain follows from:

$$
\varepsilon _ { \mathrm { c a } } \left( t \right) = \beta _ { \mathrm { a s } } ( t ) \varepsilon _ { \mathrm { c a } } ( \infty )\tag{3.11}
$$

where:

$$
\varepsilon _ { \mathsf { c a } } ( \infty ) = 2 , 5 ( f _ { \mathsf { c k } } - 1 0 ) 1 0 ^ { - 6 }\tag{3.12}
$$
  - `e12` EN1992-1-1_2004/EN1992-1-1_2004.md / 3.1.5 Stress-strain relation for non-linear structural analysis: (1) The relation between $\sigma _ { \mathsf { C } }$ and $\scriptstyle { \varepsilon _ { \mathsf { C } } }$ shown in Figure 3.2 (compressive stress and shortening strain shown as absolute values) for short term uniaxial loading is described by the Expression (3.14):

$$
\frac { \sigma _ { \mathrm { c } } } { f _ { \mathrm { c m } } } = \frac { k \eta - \eta ^ { 2 } } { 1 + \left( k - 2 \right) \eta }\tag{3.14}
$$
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
- status: needs_human_review
- reference_answer: 保护层的用途涉及黏结传力、钢筋耐腐蚀和耐火；计算时先按设计使用寿命、暴露等级和 ERC 从相应表格确定 c_min,dur。然后计算 c_min=max{c_min,dur+ΣΔc；c_min,b；10 mm}；ΣΔc 需按适用情况考虑短使用寿命、压实或养护、预应力筋、附加保护措施及磨蚀等调整。最后取 c_nom=c_min+Δc_dev，其中 Δc_dev 为施工规范允许负偏差的绝对值。
- `claim_1` [supported]: 名义保护层 c_nom 等于最小保护层 c_min 加施工偏差设计余量 Δc_dev。
  evidence: evidence_1
- `claim_2` [supported]: 最小保护层 c_min 取耐久性保护层（含适用调整量）、黏结保护层和 10 mm 三者中的最大值。
  evidence: evidence_2
- `claim_3` [supported]: 耐久性最小保护层 c_min,dur 与设计使用寿命、暴露等级和暴露抵抗等级（ERC）有关。
  evidence: evidence_3
- `claim_4` [supported]: 设计使用寿命不超过 30 年时，ΣΔc 包含对最小保护层的减小项。
  evidence: evidence_4
- `claim_5` [supported]: 混凝土压实更好或养护改善时，ΣΔc 包含对最小保护层的减小项。
  evidence: evidence_4
- `claim_6` [supported]: 对于预应力筋，ΣΔc 包含最小保护层的附加项。
  evidence: evidence_4
- `claim_7` [supported]: 采用附加混凝土保护或钢筋特殊保护措施时，ΣΔc 包含最小保护层的减小项。
  evidence: evidence_4
- `claim_8` [supported]: 磨蚀时，ΣΔc 包含保护层的附加项。
  evidence: evidence_4
- `claim_9` [supported]: Δc_dev 应取施工规范所规定且被接受的负偏差绝对值。
  evidence: evidence_5
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 6.5.1 Nominal cover: (1) The nominal cover shall be specified in the execution specification. It is defined as a minimum cover, $c _ { \mathrm { m i n } }$ (see 6.5.2), plus an allowance in design for deviation, $\Delta c _ { \mathrm { d e v } }$ (see 6.5.3):

$$
c _ { \mathrm { n o m } } = c _ { \mathrm { m i n } } + \Delta c _ { \mathrm { d e v } }\tag{6.1}
$$
  - `evidence_2` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 6.5.2.1 General: (1) The value for $c _ { \mathrm { m i n } }$ shall satisfy the requirements for both bond and durability:

$$
c _ { \operatorname* { m i n } } = \operatorname* { m a x } \left\{ c _ { \operatorname* { m i n } , \mathrm { d u r } } + \Sigma \Delta c ; c _ { \operatorname* { m i n } , \mathrm { b } } ; 1 0 \ : \mathrm { m m } \right\}\tag{6.2}
$$
  - `evidence_3` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 6.5.2.2 Minimum cover for durability: (1) The minimum concrete covers $c _ { \mathrm { m i n , d u r } }$ dependent on design service life, exposure class and exposure resistance class (ERC) are given in Table 6.3 (NDP) and Table 6.4 (NDP).
  - `evidence_4` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 6.5.2.1 General: $\Sigma \Delta c$ sum of the following applicable reductions and additions:

Δ<sup>c</sup> reduction of minimum cover for structures with design life of 30 years or less, see 6.5.2.2(2);

$\Delta c _ { \mathrm { m i n , e x c } }$ reduction of minimum cover for superior compaction or improved curing, see 6.5.2.2(3);

$\Delta c _ { \mathrm { m i n , p } }$ additional minimum cover for prestressing tendons, see 6.5.2.2(4);

$\Delta c _ { \mathrm { d u r , r e d 1 } }$ and $\Delta c _ { \mathrm { d u r , r e d 2 } }$

reduction of minimum cover for use of additional concrete protection or use of special measures for protection of reinforcing steel, see 6.5.2.2(5) and 6.5.2.2(9);

$\Delta c _ { \mathrm { d u r , a b r } }$ additional minimum cover for abrasion, see 6.5.2.2(6);
  - `evidence_5` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 6.5.3 Allowance in design for deviation in cover: (1) To calculate the nominal cover $c _ { \mathrm { n o m } } ,$ an addition to the minimum cover $c _ { \mathrm { m i n } }$ according to Formula (6.2) shall be made in design to allow for the deviation $\Delta c _ { \mathrm { d e v } }$ which shall be taken as the absolute value of the accepted negative deviation specified in the execution specification, e.g. given on the construction drawings (see EN 13670). Values for $\Delta c _ { \mathrm { d e v } }$ are given in Table 6.7 (NDP).
- [ ] 人工确认最小充分证据集

## Q07: 结构分析的目的是什么?
- status: needs_human_review
- reference_answer: 结构分析的目的是确定结构每一点的作用效应。
- `claim_1` [supported]: 结构分析的目的是确定结构每一点的作用效应。
  evidence: evidence_1
  - `evidence_1` EN1990_2002/EN1990_2002.md / structural analysis: procedure or algorithm for determination of action effects in every point of a structure
- [ ] 人工确认最小充分证据集

## Q08: 在哪些部位当线性应变分布的假设不成立时，可能需要进行局部分析?
- status: needs_human_review
- reference_answer: 当线性应变分布的假设不成立时，可能需要在以下部位进行局部分析：支座附近、集中荷载附近、梁柱交接处、锚固区，以及截面变化处。
- `claim_1` [supported]: 在线性应变分布假设不成立时，支座附近可能需要进行局部分析。
  evidence: evidence_1
- `claim_2` [supported]: 在线性应变分布假设不成立时，集中荷载附近可能需要进行局部分析。
  evidence: evidence_1
- `claim_3` [supported]: 在线性应变分布假设不成立时，梁柱交接处可能需要进行局部分析。
  evidence: evidence_1
- `claim_4` [supported]: 在线性应变分布假设不成立时，锚固区可能需要进行局部分析。
  evidence: evidence_1
- `claim_5` [supported]: 在线性应变分布假设不成立时，截面变化处可能需要进行局部分析。
  evidence: evidence_1
  - `evidence_1` EN1992-1-1_2004/EN1992-1-1_2004.md / 5.1.1 General requirements: (2) Local analyses may be necessary where the assumption of linear strain distribution is not valid, e.g.:

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
- status: needs_human_review
- reference_answer: 按 EN 1992-1-1:2023，fck 为在参考龄期 tref 测定的特征（5%）圆柱抗压强度；平均抗压强度 fcm = fck + 8 MPa；设计抗压强度按 fcd = ηcc · ktc · fck / γC 由 fck 折减/修正得到。
- `claim_1` [supported]: 混凝土抗压强度标准值 fck 是按 EN 206、在参考龄期 tref 测定的特征（5%）圆柱抗压强度。
  evidence: evidence_1
- `claim_2` [supported]: 平均抗压强度与标准值的关系为 fcm = fck + 8 MPa。
  evidence: evidence_2
- `claim_3` [supported]: 设计抗压强度为 fcd = ηcc · ktc · fck / γC。
  evidence: evidence_3
  - `evidence_1` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 5.1.3 Strength: (1) The compressive strength of concrete shall be denoted by concrete strength classes which relate to the characteristic (5 %) cylinder strength $f _ { \mathrm { c k } }$ of the concrete in accordance with EN 206, determined at an age $t _ { \mathrm { r e f } } .$
  - `evidence_2` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 5.1.3 Strength: fcm = fck + 8 MPa</td></tr>
  - `evidence_3` BSEN1992-1-1-2023/BSEN1992-1-1-2023.md / 5.1.6 Design assumptions: f _ { \mathrm { c d } } = \eta _ { \mathrm { c c } } \cdot k _ { \mathrm { t c } } \frac { f _ { \mathrm { c k } } } { \gamma _ { \mathrm { C } } }\tag{5.3}
- [ ] 人工确认最小充分证据集

## Q19: 钢筋的锚固长度与搭接长度受哪些因素影响？
- status: needs_human_review
- reference_answer: 钢筋的基本所需锚固长度由钢筋直径、钢筋设计应力和设计粘结应力决定。设计粘结应力涉及混凝土设计抗拉强度、粘结条件与浇筑时钢筋位置，以及钢筋直径。设计锚固长度还受钢筋形状、混凝土最小保护层、横向钢筋约束、焊接横筋和垂直劈裂面压力影响。设计搭接长度以基本所需锚固长度为基础，乘以α1、α2、α3、α5和α6；其中α6与搭接钢筋百分率ρ1有关，并有1,0至1,5的限制。
- `anchor_base_formula` [supported]: 基本所需锚固长度由钢筋直径φ、钢筋设计应力σsd和设计粘结应力fbd的比值确定。
  evidence: anchor_base_formula_ev
- `bond_concrete_strength` [supported]: 设计极限粘结应力fbd包含混凝土设计抗拉强度fctd。
  evidence: bond_concrete_strength_ev
- `bond_condition_position` [supported]: 粘结条件质量和浇筑时钢筋位置通过系数η1影响设计极限粘结应力。
  evidence: bond_condition_position_ev
- `bond_bar_diameter` [supported]: 钢筋直径通过系数η2影响设计极限粘结应力。
  evidence: bond_bar_diameter_ev
- `anchorage_form_cover` [supported]: 钢筋形状和混凝土最小保护层是设计锚固长度的系数影响因素。
  evidence: anchorage_form_cover_ev
- `anchorage_confinement_welding_pressure` [supported]: 横向钢筋约束、沿设计锚固长度的焊接横筋，以及垂直劈裂面的压力是设计锚固长度的系数影响因素。
  evidence: anchorage_confinement_welding_pressure_ev
- `lap_length_formula` [supported]: 设计搭接长度以基本所需锚固长度为基础，并乘以系数α1、α2、α3、α5和α6。
  evidence: lap_length_formula_ev
- `lap_percentage_factor` [supported]: 搭接长度系数α6由搭接钢筋百分率ρ1确定，且不得大于1,5或小于1,0。
  evidence: lap_percentage_factor_ev
  - `anchor_base_formula_ev` EN1992-1-1_2004/EN1992-1-1_2004.md / 8.4.3 Basic anchorage length: (2) The basic required anchorage length, $I _ { \mathrm { b , r q d } } ,$ for anchoring the force $A _ { \mathsf { s } , \mathsf { O } \mathsf { s } \mathsf { d } }$ in a straight bar assuming constant bond stress equal to $\pmb { f } _ { \mathrm { b d } }$ follows from:

$$
I _ { \mathrm { b , r q d } } = \left( \phi / 4 \right) \left( \sigma _ { \mathrm { s d } } / f _ { \mathrm { b d } } \right)\tag{8.3}
$$
  - `bond_concrete_strength_ev` EN1992-1-1_2004/EN1992-1-1_2004.md / 8.4.2 Ultimate bond stress: f _ { \mathrm { b d } } = 2 , 2 5 \ : \eta _ { 1 } \ : \eta _ { 2 } \ : f _ { \mathrm { c t d } }\tag{8.2}
$$

where:

fctd is the design value of concrete tensile strength according to 3.1.6 (2)P.
  - `bond_condition_position_ev` EN1992-1-1_2004/EN1992-1-1_2004.md / 8.4.2 Ultimate bond stress: $\eta _ { 1 }$ is a coefficient related to the quality of the bond condition and the position of the bar during concreting (see Figure 8.2):

$\eta _ { 1 } = 1 , 0$ when ‘good’ conditions are obtained and $\eta _ { 1 } = 0 , 7$ for all other cases and for bars in structural elements built with slip-forms, unless it can be shown that ‘good’ bond conditions exist
  - `bond_bar_diameter_ev` EN1992-1-1_2004/EN1992-1-1_2004.md / 8.4.2 Ultimate bond stress: 2 is related to the bar diameter:

$\eta _ { 2 } = 1 , 0$ for $\phi \leq 3 2$ mm

$\eta _ { 2 } = ( 1 3 2 - \phi ) / 1 0 0$ for $\phi > 3 2$ mm
  - `anchorage_form_cover_ev` EN1992-1-1_2004/EN1992-1-1_2004.md / 8.4.4 Design anchorage length: $\pmb { q } _ { 1 }$ is for the effect of the form of the bars assuming adequate cover (see Figure 8.1).

$\pmb { q } _ { 2 }$ is for the effect of concrete minimum cover (see Figure 8.3)
  - `anchorage_confinement_welding_pressure_ev` EN1992-1-1_2004/EN1992-1-1_2004.md / 8.4.4 Design anchorage length: $\pmb { q } _ { 3 }$ is for the effect of confinement by transverse reinforcement

$\pmb { q } _ { 4 }$ is for the influence of one or more welded transverse bars $( \phi _ { \mathrm { t } } > 0 , 6 \phi )$ along the design anchorage length $I _ { \mathrm { b d } }$ (see also 8.6)

$\pmb { q } _ { 5 }$ is for the effect of the pressure transverse to the plane of splitting along the design anchorage length
  - `lap_length_formula_ev` EN1992-1-1_2004/EN1992-1-1_2004.md / 8.7.3 Lap length: (1) The design lap length is:

$$
{ \cal I } _ { 0 } = \alpha _ { 1 } \alpha _ { 2 } \alpha _ { 3 } \alpha _ { 5 } \alpha _ { 6 } { \cal I } _ { \mathrm { b , r q d } } \geq { \cal I } _ { 0 , \mathrm { m i n } }\tag{8.10}
$$

where:

$I _ { \mathrm { b , r q d } }$ is calculated from Expression (8.3)
  - `lap_percentage_factor_ev` EN1992-1-1_2004/EN1992-1-1_2004.md / 8.7.3 Lap length: $a _ { 6 } ^ { \phantom { 8 } } = ( \rho _ { 1 } / 2 5 ) ^ { 0 , 5 }$ but not exceeding 1,5 nor less than 1,0, where $\rho _ { 1 }$ is the percentage of reinforcement lapped within $0 { , } 6 5 { \mathrm { ~ } } I _ { 0 }$ from the centre of the lap length considered (see Figure 8.8). Values of ${ \pmb q } _ { 6 }$ are given in Table 8.3.
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
- status: needs_human_review
- reference_answer: 单向板的设计步骤可概括为：先根据结构分析获得作用效应；进行承载能力极限状态下的弯曲和剪力验算；进行使用极限状态下的裂缝宽度控制和关键构件挠度验算；最后进行钢筋构造设计，并核对最小、最大配筋面积。
- `c1` [supported]: 单向板设计应以结构分析得到的作用效应为基础。
  evidence: e1
- `c2` [supported]: 设计步骤应包括对弯曲的承载能力极限状态验算。
  evidence: e1
- `c3` [supported]: 设计步骤应包括对剪力的承载能力极限状态验算。
  evidence: e1
- `c4` [supported]: 设计步骤应包括裂缝宽度控制计算。
  evidence: e1
- `c5` [supported]: 设计步骤应包括关键构件的挠度验算。
  evidence: e1
- `c6` [supported]: 设计最后应进行钢筋构造设计，并核对最小和最大配筋面积。
  evidence: e2
  - `e1` 1110_WS_EC2_-/1110_WS_EC2_-.md / 3.1.1. Motivation: On the basis of the effects of the actions from the structural analysis (Chapter 2), the following consider the ultimate limit state for typical bending, shear, axial and punching cases in design procedures. To satisfy also the serviceability limit state criteria the calculation for limiting the crack width and the deflection for the critical members are presented.
  - `e2` 1110_WS_EC2_-/1110_WS_EC2_-.md / 4.2.3.1 Slab AB12 for case 1: Provisions for the detailing of the reinforcement for this type of slabs are exposed in Clause 9.3. The minimum and maximum values for the reinforcement area, $A _ { s , m i n }$ and $A _ { s , m a x } ,$ are the same as for the beams [9.3.1.1 (1)]. For a slab unit width (b = 1 mm):
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
- status: needs_human_review
- reference_answer: 按 EN 1992-1-1 的抗扭设计程序，先判断结构平衡是否依赖抗扭承载力：若依赖，应同时进行承载能力极限状态和正常使用极限状态的完整抗扭设计；若扭转仅由超静定结构的变形协调产生且不影响稳定性，通常无需作承载能力极限状态抗扭验算，但应设置箍筋和纵筋形式的最小配筋以控制开裂。随后可将截面按等效薄壁闭口截面建模，计算纯扭下的壁面剪应力及各壁扭转剪力；对扭剪共同作用，叠加扭转和剪力效应并采用相同压杆倾角。再按公式(6.28)确定抗扭纵筋，受拉弦的抗扭纵筋与其他纵筋相加；最后按公式(6.29)验算混凝土压杆控制的扭剪组合承载力。对大致矩形实体截面，满足公式(6.31)时仅需最小配筋。
- `C1` [supported]: 当结构的静力平衡依赖构件抗扭承载力时，应进行覆盖承载能力极限状态和正常使用极限状态的完整抗扭设计。
  evidence: E1
- `C2` [supported]: 对仅因变形协调而产生扭转、且结构稳定性不依赖抗扭承载力的超静定结构，通常无需在承载能力极限状态考虑扭转。
  evidence: E2
- `C3` [supported]: 上述仅需协调扭转的情况，应按第7.3和第9.2节设置由箍筋和纵向钢筋组成的最小配筋，以防止过度开裂。
  evidence: E2
- `C4` [supported]: 抗扭承载力可按闭合剪流满足平衡的薄壁闭口截面计算；实体截面可等效为薄壁截面。
  evidence: E3
- `C5` [supported]: 纯扭矩下，截面壁的扭转剪应力应按公式(6.26)计算，墙肢 i 的扭转剪力应按公式(6.27)计算。
  evidence: E4
- `C6` [supported]: 空心和实体构件的扭转与剪力效应可叠加，并假定压杆倾角取相同值。
  evidence: E5
- `C7` [supported]: 扭转所需纵向钢筋截面面积之和可按公式(6.28)计算；受拉弦中的抗扭纵筋应与其他钢筋相加。
  evidence: E6
- `C8` [supported]: 受扭和受剪构件须满足公式(6.29)，以使由混凝土压杆承载力控制的最大承载力不被超过。
  evidence: E7
- `C9` [supported]: 大致矩形实体截面在满足公式(6.31)时仅需最小配筋。
  evidence: E8
  - `E1` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.3.1 General: (1)P Where the static equilibrium of a structure depends on the torsional resistance of elements of the structure, a full torsional design covering both ultimate and serviceability limit states shall be made.
  - `E2` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.3.1 General: (2) Where, in statically indeterminate structures, torsion arises from consideration of compatibility only, and the structure is not dependent on the torsional resistance for its stability, then it will normally be unnecessary to consider torsion at the ultimate limit state. In such cases a minimum reinforcement, given in Sections 7.3 and 9.2, in the form of stirrups and longitudinal bars should be provided in order to prevent excessive cracking.
  - `E3` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.3.1 General: (3) The torsional resistance of a section may be calculated on the basis of a thin-walled closed section, in which equilibrium is satisfied by a closed shear flow. Solid sections may be modelled by equivalent thin-walled sections.
  - `E4` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.3.2 Design procedure: (1) The shear stress in a wall of a section subject to a pure torsional moment may be calculated from:

$$
\tau _ { \mathrm { t , i } } t _ { \mathrm { e f , i } } = \frac { T _ { \mathrm { E d } } } { 2 A _ { \mathrm { k } } }\tag{6.26}
$$

The shear force $V _ { \sf E d , i }$ in a wall i due to torsion is given by:

$$
V _ { \sf E d , i } = \tau _ { { \sf t } , { \sf i } } t _ { { \sf e f } , { \sf i } } z _ { \sf i }\tag{6.27}
$$
  - `E5` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.3.2 Design procedure: (2) The effects of torsion and shear for both hollow and solid members may be superimposed, assuming the same value for the strut inclination . The limits for  given in 6.2.3 (2) are also fully applicable for the case of combined shear and torsion.
  - `E6` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.3.2 Design procedure: (3) The required cross-sectional area of the longitudinal reinforcement for torsion $\Sigma A _ { \mathsf { s l } }$ may be calculated from Expression (6.28):

$$
\frac { \sum A _ { \mathrm { s l } } \mathsf { f } _ { \mathrm { y d } } } { u _ { \mathrm { k } } } = \frac { T _ { \mathrm { E d } } } { 2 A _ { \mathrm { k } } } \mathsf { c o t } \theta\tag{6.28}
$$

where

$u _ { \mathsf { k } }$ is the perimeter of the area $A _ { \mathsf { k } }$

$\pmb { f } _ { \mathsf { y d } }$ is the design yield stress of the longitudinal reinforcement $A _ { \mathsf { s l } }$

$\theta$ is the angle of compression struts (see Figure 6.5).

In compressive chords, the longitudinal reinforcement may be reduced in proportion to the available compressive force. In tensile chords the longitudinal reinforcement for torsion should be added to the other reinforcement.
  - `E7` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.3.2 Design procedure: (4) The maximum resistance of a member subjected to torsion and shear is limited by the capacity of the concrete struts. In order not to exceed this resistance the following condition should be satisfied:

$$
T _ { \mathsf { E d } } / T _ { \mathsf { R d , m a x } } + V _ { \mathsf { E d } } / V _ { \mathsf { R d , m a x } } \leq 1 , 0\tag{6.29}
$$
  - `E8` EN1992-1-1_2004/EN1992-1-1_2004.md / 6.3.2 Design procedure: (5) For approximately rectangular solid sections only minimum reinforcement is required (see 9.2.1.1) provided that the following condition is satisfied:

$$
T _ { \mathrm { E d } } / T _ { \mathrm { R d , c } } + V _ { \mathrm { E d } } / V _ { \mathrm { R d , c } } \leq 1 , 0\tag{6.31}
$$
- [ ] 人工确认最小充分证据集

## Q31: 其他通用问题：
- status: needs_human_review
- reference_answer: 语料不足以回答：题目未提供具体问题，无法生成针对性的 Eurocode 参考答案。
- `claim_1` [corpus_gap]: 题目仅给出“其他通用问题：”，未包含任何具体的技术问题或待判断事项；因此无法从已完整检索的语料中形成针对性的、可证据支持的回答。
  evidence: (none)
- [ ] 人工确认最小充分证据集
