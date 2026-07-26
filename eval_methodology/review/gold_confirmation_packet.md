# Gold 人工确认包（CRec sign-off）

复核目标：判断每题的证据集是否**最小且充分**地支持 gold claims。
引用是否逐字存在于语料已由脚本确定性校验（下表 quote_found 列），
✗ 的条目必须驳回或修正后再确认。

确认命令：
```bash
uv run python -m eval_methodology.mvp.dataset.confirm_gold confirm \
    --ids Q01,Q04 --reviewer <你的名字>
```

## Q01 — unreviewed

**问题**：请给出混凝土结构设计中相关作用荷载和材料的分项系数。

**Gold claims**：

- [supported] 承载能力极限状态设计中，永久作用的典型分项系数 γG 为 1.35。
- [supported] 承载能力极限状态设计中，可变作用的典型分项系数 γQ 为 1.50。
- [supported] 按 EN 1990 式 (6.10a)/(6.10b) 的典型 STR 组合，永久荷载、使用荷载和风荷载的系数会随主导作用变化，例如永久+使用荷载可取 1.35G+1.05Q 或 1.25G+1.50Q，伴随可变作用可取 0.75。
- [supported] 混凝土的材料分项系数 γc 为 1.50。
- [supported] 钢筋的材料分项系数 γs 为 1.15。
- [supported] 正常使用极限状态计算中，材料性能的分项系数通常取 1.0。
- [supported] 分项系数的最终取值应结合相应国家附录确定。

**证据（最小充分性由你判断）**：

- `ev01` ✓ `EN1990_2002/EN1990_2002.md` — EN 1990:2002 (E)
  > (*) Variable actions are those considered in Table A1.1 NOTE 1 The γ values may be set by the National annex. The recommended set of values for γ are :  $\gamma _ { \mathrm { G j , s u p } } = 1 , 1 0$   $\gamma _ { \mathrm { G j , i n f } } = 0 { , } 9 0$   $…
- `ev02` ✓ `EN1990_2002/EN1990_2002.md` — A1.3.2 Design values of actions in the accidental and seismic design situations
  > (1) The partial factors for actions for the ultimate limit states in the accidental and seismic design situations (expressions 6.11a to 6.12b) should be 1,0. - values are given in Table A1.1.
- `ev03` ✓ `EN1990_2002/EN1990_2002.md` — A1.4.1 Partial factors for actions
  > (1) For serviceability limit states the partial factors for actions should be taken as 1,0 except if differently specified in EN 1991 to EN 1999.
- `ev04` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 2.4.2.4 Partial factors for materials
  > <table><tr><td rowspan=1 colspan=1>Design situations</td><td rowspan=1 colspan=1>Yc for concrete</td><td rowspan=1 colspan=1>Ys for reinforcing steel</td><td rowspan=1 colspan=1>Yys for prestressing steel</td></tr><tr><td rowspan=1 colspan=1>Persistent&amp;Tra…

## Q03 — unreviewed

**问题**：有哪些因素会对混凝土的徐变与收缩产生影响?

**Gold claims**：

- [supported] 环境湿度或气候条件会影响混凝土徐变与收缩。
- [supported] 构件尺寸会影响混凝土徐变与收缩。
- [supported] 构件的尺寸和形状会影响干燥收缩的发展。
- [supported] 构件温度会影响干燥收缩的发展。
- [supported] 混凝土组成会影响混凝土徐变与收缩。
- [supported] 基本收缩与水灰比以及由此相关的混凝土强度有关。
- [supported] 首次施加荷载时混凝土的龄期或成熟度会影响徐变。
- [supported] 荷载的持续时间会影响混凝土徐变。
- [supported] 荷载或压应力的大小会影响混凝土徐变；较高压应力下需考虑徐变的非线性发展。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `BSEN1992-1-1-2023/BSEN1992-1-1-2023.md` — B.3 General
  > NOTE 1 Both creep and shrinkage are subdivided into two components, basic creep and drying creep or basic shrinkage and drying shrinkage, respectively, due to the pronounced effect of the ambient climate conditions on the magnitude and the kinetics of the time…
- `evidence_2` ✓ `BSEN1992-1-1-2023/BSEN1992-1-1-2023.md` — B.3 General
  > NOTE 2 The drying shrinkage strain develops slowly, since it is a function of the diffusion controlled migration of the water through the hardened concrete, which is affected by the size and shape, and the temperature of the member. The basic shrinkage strain …
- `evidence_3` ✓ `BSEN1992-1-1-2023/BSEN1992-1-1-2023.md` — B.5 Basic formulae for determining the creep coefficient
  > $\beta _ { \mathrm { d c } , f _ { \mathrm { c m } } }$ is a function to describe the effect of concrete strength on drying creep, see Formula (B.10);

$\beta _ { \mathrm { d c , R H } }$ is a function to describe the effect of relative humidity and notional s…

## Q04 — unreviewed

**问题**：钢筋的主要特性有哪些?并给出相应总结。

**Gold claims**：

- [supported] 钢筋的主要强度特性包括屈服强度或0.2%规定塑性延伸强度。
- [supported] 钢筋的性能还包括最大实际屈服强度和抗拉强度。
- [supported] 钢筋延性可由最大荷载时伸长率以及抗拉强度与屈服强度之比表征。
- [supported] 钢筋的弯曲性能是其规定特性之一。
- [supported] 钢筋与混凝土之间的黏结性能是钢筋的主要特性之一。
- [supported] 钢筋的截面尺寸及尺寸公差属于需要规定的特性。
- [supported] 疲劳强度是钢筋的重要性能，可通过疲劳S-N曲线描述。
- [supported] 可焊性是钢筋的规定特性之一。
- [supported] 对于焊接钢筋网和钢筋桁架，还需考虑剪切强度与焊点强度。
- [supported] 设计时至少应明确钢筋的强度等级、延性等级以及直径或规格。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 3.2.2 Properties
  > (1)P The behaviour of reinforcing steel is specified by the following properties:

\- yield strength $( f _ { \mathrm { y k } } \circ \mathsf { r } f _ { 0 , 2 \mathrm { k } } )$

\- maximum actual yield strength $( \pmb { f } _ { \mathsf { y } , \mathsf { m a…
- `evidence_2` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 3.2.2 Properties
  > (4)P The surface characteristics of ribbed bars shall be such to ensure adequate bond with the concrete.

(5) Adequate bond may be assumed by compliance with the specification of projected rib area, $\pmb { f } _ { \mathsf { R } } .$

Note: Minimum values of t…
- `evidence_3` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 3.2.2 Properties
  > \- bendability

\- bond characteristics $( { f } _ { \mathsf { R } } ;$ See Annex C)

\- section sizes and tolerances

\- fatigue strength

\- weldability

\- shear and weld strength for welded fabric and lattice girders

## Q07 — unreviewed

**问题**：结构分析的目的是什么?

**Gold claims**：

- [supported] 结构分析用于确定整个结构或其某一部分中的内力和弯矩分布。
- [supported] 结构分析也可用于确定整个结构或其某一部分中的应力、应变和位移分布。
- [supported] 结构分析所得结果可作为后续结构或截面验算的作用效应。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `EN1990_2002/EN1990_2002.md` — structural analysis
  > procedure or algorithm for determination of action effects in every point of a structure

## Q08 — unreviewed

**问题**：在哪些部位当线性应变分布的假设不成立时，可能需要进行局部分析?

**Gold claims**：

- [supported] 支座附近可能需要进行局部分析。
- [supported] 集中荷载作用处可能需要进行局部分析。
- [supported] 梁柱交汇处可能需要进行局部分析。
- [supported] 锚固区可能需要进行局部分析。
- [supported] 截面变化处可能需要进行局部分析。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 5.1.1 General requirements
  > (2) Local analyses may be necessary where the assumption of linear strain distribution is not valid, e.g.:

in the vicinity of supports

local to concentrated loads

in beam-column intersections

in anchorage zones

at changes in cross section.

## Q09 — unreviewed

**问题**：根据性质和功能，结构构件包括哪些类型?

**Gold claims**：

- [supported] 按性质和功能，结构构件包括梁。
- [supported] 按性质和功能，结构构件包括柱。
- [supported] 按性质和功能，结构构件包括楼板（slabs）。
- [supported] 按性质和功能，结构构件包括墙。
- [supported] 按性质和功能，结构构件包括板（plates）。
- [supported] 按性质和功能，结构构件包括拱。
- [supported] 按性质和功能，结构构件包括壳。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 5.3.1 Structural models for overall analysis
  > (1)P The elements of a structure are classified, by consideration of their nature and function, as beams, columns, slabs, walls, plates, arches, shells etc. Rules are provided for the analysis of the commoner of these elements and of structures consisting of c…

## Q12 — unreviewed

**问题**：混凝土受压区应变-应力分布假设是什么？

**Gold claims**：

- [supported] 截面在受力后仍保持平面，因此混凝土应变沿截面高度呈线性分布。
- [supported] 混凝土受压应力应根据规范规定的设计应力分布确定。
- [supported] 受压区可采用抛物线—矩形应力分布：上升段为 σcd = fcd[1-(1-εc/εc2)^2]，随后为恒定应力 fcd。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `BSEN1992-1-1-2023/BSEN1992-1-1-2023.md` — 8.1.1 General
  > (2) When determining the ultimate moment resistance of reinforced or prestressed concrete crosssections, the following assumptions shall be made:

— plane sections remain plane;
- `evidence_2` ✓ `BSEN1992-1-1-2023/BSEN1992-1-1-2023.md` — 8.1.2 Stress distribution in the compression zones
  > (1) For the design of cross-sections, the following stress distribution may be used, see Figure 8.2c) (compressive strain shown positive):

$$
\sigma _ { \mathrm { c d } } = \left\{ \begin{array} { c } { f _ { \mathrm { c d } } \left[ 1 - \left( 1 - \frac { \v…
- `evidence_3` ✓ `BSEN1992-1-1-2023/BSEN1992-1-1-2023.md` — 8.1.2 Stress distribution in the compression zones
  > (2) Alternatively, a rectangular stress block distribution as given in Figure 8.2d) may be assumed.

## Q13 — unreviewed

**问题**：混凝土压碎应变限值是多少？

**Gold claims**：

- [supported] 混凝土的极限压缩应变（压碎应变限值）εcu 为 0.0035，即 3.5‰。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `BSEN1992-1-1-2023/BSEN1992-1-1-2023.md` — 5.1.6 Design assumptions
  > $$
\varepsilon _ { \mathrm { c } } < \varepsilon _ { \mathrm { c u 1 } } [ \% _ { 0 } ] = 2 , 8 + 1 4 \cdot ( 1 - f _ { \mathrm { c m } } / 1 0 8 ) ^ { 4 } \leq 3 , 5 \ \%\tag{5.10}
$$

## Q14 — unreviewed

**问题**：极限受力状态下混凝土受压区高度限值为多少？

**Gold claims**：

- [supported] 对于 C50/60 及以下强度等级的混凝土，极限状态下受压区相对高度限值为 x/d ≤ 0.45。
- [supported] 对于 C55/67 及以上强度等级的混凝土，极限状态下受压区相对高度限值为 x/d ≤ 0.35。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 5.6.3 Rotation capacity
  > (2) In regions of yield hinges, $x _ { \mathrm { u } } / d$ shall not exceed the value 0,45 for concrete strength classes less than or equal to C50/60, and 0,35 for concrete strength classes greater than or equal to C55/67.

## Q15 — unreviewed

**问题**：弯矩重分布限值为多少？

**Gold claims**：

- [supported] 弯矩重分布系数 δ 是重分布后弯矩与重分布前弯矩之比。
- [supported] 采用 B 级或 C 级钢筋时，δ 不得小于 0.70，因此弯矩重分布幅度不得超过 30%。
- [supported] 采用 A 级钢筋时，δ 不得小于 0.80，因此弯矩重分布幅度不得超过 20%。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `BSEN1992-1-1-2023/BSEN1992-1-1-2023.md` — 7.3.2 Linear elastic analysis with redistribution
  > $\geq 0 , 7$ where Class B or Class C reinforcing steel or prestressing steel is used (see Table 5.5);

$\ge 0 , 8$ where Class A reinforcing steel is used (see Table 5.5).

## Q17 — unreviewed

**问题**：截面计算中材料分项安全系数为多少？

**Gold claims**：

- [supported] 钢结构截面承载力计算的材料分项安全系数为 γM0 = 1.0。
- [supported] EC3 的材料分项安全系数可能由国家附录规定，因此具体工程应核对适用的国家附录。

**证据（最小充分性由你判断）**：

- `e1` ✓ `BSEN1992-1-1-2023/BSEN1992-1-1-2023.md` — 4.3.3 Partial factors for materials
  > <table><tr><td rowspan=1 colspan=1>Design situations —Limit states</td><td rowspan=1 colspan=1>γs for reinforcing andprestressing steel</td><td rowspan=1 colspan=1>γcand $\gamma _ { \mathbf { C E } }$ forconcrete</td><td rowspan=1 colspan=1>γv for shear and pu…

## Q20 — unreviewed

**问题**：什么情况下需要考虑二阶效应？

**Gold claims**：

- [supported] 当二阶效应可能显著影响结构整体稳定性或关键截面达到承载能力极限状态时，应考虑二阶效应。
- [supported] 对于混凝土结构，二阶效应超过相应一阶效应的10%时，不能按规范的简化条件忽略。
- [supported] 对于独立受压构件，当长细比 λ 达到或超过限值 λ_lim 时，应考虑二阶效应；低于该限值时可忽略。
- [supported] 双向弯曲时，可在各主弯曲平面分别检查长细比，并只在超过长细比限值的方向考虑二阶效应。
- [supported] 柱、墙、桩、拱、壳等受轴力且其行为明显受变形影响的构件或结构，以及采用柔性支撑体系的结构，需要重点检查二阶效应。
- [supported] 对于钢结构，当变形显著增大作用效应或显著改变结构行为时，应考虑二阶效应。
- [supported] 对于钢结构，以弹性临界荷载系数判断时，α_cr≤10通常需要考虑二阶效应。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `EN1993-1-1_2005/EN1993-1-1_2005.md` — 5.2.1 Effects of deformed geometry of the structure
  > (2) The effects of the deformed geometry (second-order effects) should be considered if they increase the action effects significantly or modify significantly the structural behaviour.
- `evidence_2` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 5.1.4 Second order effects
  > (1)P Second order effects (see EN 1990 Section 1) shall be taken into account where they are likely to affect the overall stability of a structure significantly and for the attainment of the ultimate limit state at critical sections.

## Q23 — unreviewed

**问题**：预应力在各类极限状态下的影响是什么

**Gold claims**：

- [supported] 预应力应归类为永久作用。
- [supported] 预应力效应可作为外部作用，也可作为由预应变和预曲率形成的抗力考虑。
- [supported] 预应力应进入作用组合，其效应应计入施加于结构的内力矩和轴力。
- [supported] 承载能力极限状态验算中，预应力在多数情况下属于有利效应，应采用有利预应力分项系数；持久和暂时设计状况的推荐值为1.0。
- [supported] 外预应力稳定极限状态中，预应力增大可能产生不利影响，此时应采用不利预应力值；规范推荐的整体分析分项系数为1.3。
- [supported] 预应力局部效应验算应采用不利预应力分项系数。
- [supported] ULS抗弯验算中，若预应力作为外部作用，预应力筋抗力应限于设计强度减去已有设计预应力应力；若预应力在抗力侧考虑，则可限于预应力筋完整设计强度。
- [supported] 应避免预应力筋失效导致构件发生脆性破坏。
- [supported] 正常使用极限状态中，预应力应按相应作用组合计入；裂缝控制所用轴力应考虑预应力特征值。
- [supported] 预应力宜用上、下特征值表示；对于ULS，在其他 Eurocode 允许时可采用单一特征值。
- [supported] 用于ULS的有利预应力分项系数推荐值1.0也可用于疲劳验算。
- [supported] 各极限状态验算采用的有效预应力应考虑位置、时间、即时损失和长期损失的影响。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 5.10.1 General
  > (2) The effects of prestressing may be considered as an action or a resistance caused by prestrain and precurvature. The bearing capacity should be calculated accordingly.

(3) In general prestress is introduced in the action combinations defined in EN 1990 as…
- `evidence_2` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 5.10.8 Effects of prestressing at ultimate limit state
  > (1) In general the design value of the prestressing force may be determined by $P _ { \mathrm { d , t } } ( \mathsf { x } ) =$ $\varkappa _ { \sf P } , P _ { \sf m , t } ( \sf x )$ (see 5.10.3 (4) for the definition of $P _ { \mathrm { m , t } } ( \mathsf { x …
- `evidence_3` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 5.10.9 Effects of prestressing at serviceability limit state and limit state of fatigue
  > $( 1 ) \mathsf { P }$ For serviceability and fatigue calculations allowance shall be made for possible variations in prestress. Two characteristic values of the prestressing force at the serviceability limit state are estimated from:

$$
P _ { \mathrm { k , s …
- `evidence_4` ✓ `EN1990_2002/EN1990_2002.md` — 6.4.3.3 Combinations of actions for accidental design situations
  > (1) The general format of effects of actions should be :

$$
E _ { d } = E \Big \{ G _ { k , j } ; P ; A _ { d } ; ( \psi _ { 1 , 1 } \mathrm { o r } \psi _ { 2 , 1 } ) Q _ { k , 1 } ; \psi _ { 2 , i } Q _ { k , i } \Big \} \quad j \geq 1 ; i > 1\tag{6.11a}
$$
- `evidence_5` ✓ `EN1990_2002/EN1990_2002.md` — 6.4.3.4 Combinations of actions for seismic design situations
  > (1) The general format of effects of actions should be :

$$
E _ { d } = E \Big \{ G _ { k , j } ; P ; A _ { E d } ; \psi _ { 2 , i } Q _ { k , i } \Big \} \quad j \geq 1 ; i \geq 1\tag{6.12a}
$$

## Q24 — unreviewed

**问题**：剪应力一般验证程序是怎样的

**Gold claims**：

- [supported] 剪切承载力应在所有关键控制截面进行验证。
- [supported] 当 τEd ≤ 2τRdc,min 时，可以省略详细抗剪验算。
- [supported] 当 τEd ≤ τRd,c 时，不需要按计算配置抗剪钢筋。
- [supported] 当 τEd > τRd,c 时，应按相应条款设计抗剪钢筋。
- [supported] 即使计算上不需要抗剪钢筋，线性构件仍可能需要按第12条配置最小抗剪钢筋。
- [supported] 对于静定结构中有效高度 d > 500 mm 的线性构件，应配置最小抗剪钢筋。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 6.2.1 General verification procedure
  > $V _ { \sf R d , c }$ is the design shear resistance of the member without shear reinforcement.

$V _ { \sf R d , s }$ is the design value of the shear force which can be sustained by the yielding shear reinforcement.

$V _ { \sf R d , m a x }$ is the design v…
- `evidence_2` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 6.2.1 General verification procedure
  > (3) In regions of the member where $V _ { \sf E d } \leq V _ { \sf R d , c }$ no calculated shear reinforcement is necessary. $V _ { \mathsf { E d } }$ is the design shear force in the section considered resulting from external loading and prestressing (bonded…
- `evidence_3` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 6.2.1 General verification procedure
  > (4) When, on the basis of the design shear calculation, no shear reinforcement is required, minimum shear reinforcement should nevertheless be provided according to 9.2.2. The minimum shear reinforcement may be omitted in members such as slabs (solid, ribbed o…
- `evidence_4` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 6.2.1 General verification procedure
  > (5) In regions where $V _ { \sf E d } > V _ { \sf R d , c }$ according to Expression (6.2), sufficient shear reinforcement should be provided in order that $V _ { \sf E d } \leq V _ { \sf R d }$ (see Expression (6.8)).

(6) The sum of the design shear force an…
- `evidence_5` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 6.2.1 General verification procedure
  > (7) The longitudinal tension reinforcement should be able to resist the additional tensile force caused by shear (see 6.2.3 (7)).

## Q29 — unreviewed

**问题**：需要设计剪力筋的构件有什么特征

**Gold claims**：

- [supported] 当构件某区域的设计剪力 V_Ed 超过无剪力筋时的设计抗剪承载力 V_Rd,c，该区域需要进行剪力筋计算设计。
- [supported] 需要剪力筋的构件按桁架模型进行抗剪设计。
- [supported] 剪力筋与构件纵轴的夹角应为 45°～90°。
- [supported] 剪力筋可由箍筋、弯起钢筋，或在受压区和受拉区适当锚固的钢筋笼、梯架等组成。

**证据（最小充分性由你判断）**：

- `evidence_1` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 6.2.1 General verification procedure
  > (5) In regions where $V _ { \sf E d } > V _ { \sf R d , c }$ according to Expression (6.2), sufficient shear reinforcement should be provided in order that $V _ { \sf E d } \leq V _ { \sf R d }$ (see Expression (6.8)).
- `evidence_2` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 6.2.3 Members requiring design shear reinforcement
  > (1) The design of members with shear reinforcement is based on a truss model (Figure 6.5).
- `evidence_3` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 6.2.3 Members requiring design shear reinforcement
  > (3) For members with vertical shear reinforcement, the shear resistance, $V _ { \mathrm { R d } }$ is the smaller value of:
- `evidence_4` ✓ `EN1992-1-1_2004/EN1992-1-1_2004.md` — 6.2.1 General verification procedure
  > (7) The longitudinal tension reinforcement should be able to resist the additional tensile force caused by shear (see 6.2.3 (7)).
