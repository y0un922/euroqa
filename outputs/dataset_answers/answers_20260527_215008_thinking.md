# 层级分类问题集答案

- 生成时间: 2026-05-27T21:52:30
- 问题集: `/Users/youngz/Downloads/(层级分类)问题集_20260518.xlsx`
- 系统接口: `http://127.0.0.1:18080/api/v1/query/stream`
- thinking: `True`
- 有效问题数: 32

## 1. 请给出混凝土结构设计中相关作用荷载和材料的分项系数。

- Excel 行号: 2
- 层级: Level 1 / 基础概念与符号体系层

### 答案

在混凝土结构设计中，作用（荷载）和材料的分项系数主要依据 EN 1990（结构设计基础）和 EN 1992-1-1（混凝土结构设计）确定。规范提供了推荐值，但具体取值必须结合项目所在国的**国家附录（National Annex）** 确定。

以下为基于规范原文整理的分项系数取值规则及推荐值：

### 一、 作用（荷载）的分项系数
一般作用（如恒载、活载、风载等）的分项系数及荷载组合规则由 EN 1990 及其规范性附录（如建筑附录 A1、桥梁附录 A2）统一规定 [Ref-1] [Ref-2] [Ref-6]。对于混凝土结构中的特定作用，EN 1992-1-1 给出了以下补充规定：

1. **收缩作用（Shrinkage actions）**
   - 承载能力极限状态（ULS）下若需考虑收缩作用，分项系数 $\gamma_{SH}$ 的推荐值为 **1.0** [Ref-2] [Ref-13]。
2. **预应力（Prestress）**
   restress）**
   - **有利情况**（持久和瞬态设计情况，以及疲劳验算）：分项系数 $\gamma_{P,fav}$ 推荐值为 **1.0** [Ref-2] [Ref-13]。
   - **不利情况**（外部预应力整体稳定性验算）：分项系数 $\gamma_{P,unfav}$ 推荐值为 **1.3** [Ref-2] [Ref-13]。
   - **不利情况**（局部效应验算）：分项系数 $\gamma_{P,unfav}$ 推荐值为 **1.2** [Ref-2] [Ref-13]。
3. **疲劳荷载（Fatigue loads）**
   - 疲劳荷载分项系数 $\gamma_{F,fat}$ 的推荐值为 **1.0** [Ref-2] [Ref-13]。
4. **正常使用极限状态（SLS）**
   - 在正常使用极限状态验算中，荷载（作用）的分项系数通常取 **1.0** [Ref-20]。

### 二、 材料的分项系数
1. **承载能力极限状态（ULS）**
   - 混凝土（$\gamma_C$）和钢筋（$\gamma_S$）的分项系数推荐值详见规范 **Table 2.1N**（区分了“持久与瞬态”及“偶然”设计情况） [Ref-2] [Ref-5] [Ref-9] [Ref-13]。
   - **疲劳验算**：推荐使用 Table 2.1N 中“持久设计情况”的值作为疲劳材料分项系数 $\gamma_{C,fat}$ 和 $\gamma_{S,fat}$ [Ref-2] [Ref-5] [Ref-9] [Ref-13]。
   - **现浇无永久护筒灌注桩**：计算其设计抗力时，混凝土分项系数 $\gamma_C$ 需乘以附加系数 $k_f$，推荐值为 **1.1** [Ref-2] [Ref-13]。
2. **正常使用极限状态（SLS）**
   - 材料分项系数应取 EN 1992-1-1 特定条款中给出的值 [Ref-2] [Ref-5] [Ref-9] [Ref-13]。
   - 对于规范特定条款未涵盖的情况，材料分项系数推荐取 **1.0** [Ref-2] [Ref-5] [Ref-9] [Ref-13] [Ref-20]。
3. **分项系数的折减条件**
   - 如果采取了能够降低计算抗力不确定性的有效措施，允许使用较低的 $\gamma_C$ 和 $\gamma_S$ 值（具体指导可参考规范资料性附录 A） [Ref-2] [Ref-5] [Ref-9] [Ref-13]。

### 三、 土（地基）的属性
- 土的强度属性设计值不属于 EN 1992 的管辖范围，必须按照 **EN 1997（岩土工程设计）** 的规定进行计算 [Ref-2] [Ref-13]。

---

### ⚠️ 重要适用条件与限制提醒
1. **国家附录（NDP）优先**：上述所有提到的推荐值（包括 $\gamma_{SH}$、$\gamma_P$、$\gamma_{F,fat}$、$\gamma_C$、$\gamma_S$ 及 $k_f$）均属于“国家确定参数（NDPs）”。在实际工程中，**必须查阅项目所在国的国家附录（National Annex）** 以获取法定强制取值，国家附录可能会修改这些推荐值 [Ref-2] [Ref-5] [Ref-9] [Ref-11] [Ref-13]。
2. **防火设计除外**：Table 2.1N 中给出的材料分项系数**不适用**于防火设计。混凝土结构的防火设计必须参考 **EN 1992-1-2** 中的专门规定 [Ref-2] [Ref-5] [Ref-9] [Ref-13]。
3. **可靠性等级**：使用本规范及 EN 1990 附录中给定的分项系数进行设计，默认对应于 **RC2 可靠性等级** 的结构。若项目属于其他可靠性等级，需按 EN 1990 调整 [Ref-3]。

### 来源

- [1] DG_EN1992-1-1__-1-2，页 17，条款 : All Eurocodes rely on EN 1990 for the basis of structural design. The provisions of that code are applicable to all materials, and as such only the requirements which are independent of material properties are noted. In the main it
- [2] EN1992-1-1_2004，页 23，条款 2.4.1, 2.4.2.1: (1) The rules for the partial factor method are given in EN 1990 Section 6. (1) Where consideration of shrinkage actions is required for ultimate limit state a partial factor, SH, should be used. Note: The value of $\gamma _ { \mathsf { S
- [3] EN1992-1-1_2004，页 20，条款 2.1.1, (1)P: (1)P The design of concrete structures shall be in accordance with the general rules given in EN 1990. (2)P The supplementary provisions for concrete structures given in this section shall also be applied. (3) The basic requirements of EN
- [4] DG EN1990，页 128，条款 : Due, largely, to increased competition among material producers, there has been a tendency within the construction industry to reduce safety margins (in particular partial factors) for both actions and material resistance. This together
- [5] EN1992-1-1_2004，页 24，条款 2.4.2.4: (1) Partial factors for materials for ultimate limit states, $\textstyle \gamma _ { \mathsf { C } }$ and $\gamma _ { \mathsf { S } }$ should be used. Note: The values of C and $\gamma _ { \mathsf { S } }$ for use in a Country may be found
- [6] DG EN1990，页 17，条款 1.1.1: EN 1990, ‘Eurocode: basis of structural design’, is the head document in the Eurocode suite, and it establishes for all the structural Eurocodes the principles and requirements for safety, serviceability and durability of structures; it
- [7] EN1992-1-1_2004，页 2，条款 1.1.1, (1)P: 1. General 1.1 Scope 1.1.1 Scope of Eurocode 2 1.1.2 Scope of Part 1-1 of Eurocode 2 1.2 Normative references 1.2.1 General reference standards 1.2.2 Other reference standards 1.3 Assumptions 1.4 Distinction between principles and
- [8] DG_EN1990，页 17，条款 1.1.1, 1.1.2: EN 1990, ‘Eurocode: basis of structural design’, is the head document in the Eurocode suite, and it establishes for all the structural Eurocodes the principles and requirements for safety, serviceability and durability of structures; it

## 2. 请给出混凝土材料的强度与变形的相关定义、相互关系及如何计算。

- Excel 行号: 3
- 层级: Level 1 / 基础概念与符号体系层

### 答案

基于欧洲规范 EN 1992-1-1（Eurocode 2）及相关设计指南，混凝土（concrete）的强度（strength）与变形（deformation）的定义、相互关系及计算方法整理如下：

### 一、 混凝土强度的定义与计算
1. **特征强度（Characteristic Strength）**
   - 混凝土抗压强度由强度等级表示，对应于28天龄期的特征圆柱体强度 $f_{ck}$ 或立方体强度 $f_{ck,cube}$ [Ref-12], [Ref-19]。特征强度是指不超过5%的测试结果可能低于该值的强度（即5%分位值） [Ref-19]。
   - 平均抗压强度 $f_{cm}$ 与特征强度的关系为：$f_{cm} = f_{ck} + 8 \text{ (MPa)}$ [Ref-2]。
2. **设计强度（Design Strength）**
   - **设计抗压强度**：$f_{cd} = \alpha_{cc} f_{ck} / \gamma_c$ [Ref-12], [Ref-19]。其中 $\alpha_{cc}$ 为考虑长期效应及加载方式不利影响的系数，规范推荐值为 1.0（注：英国国家附录推荐值为 0.85） [Ref-19]；$\gamma_c$ 为混凝土材料分项系数。
   - **设计抗拉强度**：强度：$f_{ctd} = \alpha_{ct} f_{ctk,0.05} / \gamma_c$ [Ref-12], [Ref-19]。$\alpha_{ct}$ 推荐值为 1.0 [Ref-19]。

### 二、 混凝土变形的定义与计算
混凝土的变形主要包括弹性变形、徐变和收缩：
1. **弹性变形（Elastic Deformation）**
   - **弹性模量（$E_{cm}$）**：定义为应力 $\sigma_c = 0$ 到 $0.4 f_{cm}$ 之间的割线模量 [Ref-12]。规范给出的基准值适用于**石英岩骨料**；若使用石灰岩骨料需降低10%，砂岩骨料降低30%，玄武岩骨料增加20% [Ref-12], [Ref-19]。其估算公式为：$E_{cm} = 22 \times [(f_{cm})/10]^{0.3}$ （$f_{cm}$ 单位为 MPa，$E_{cm}$ 单位为 GPa） [Ref-2]。
   - **泊松比**：未开裂混凝土取 0.2，开裂混凝土取 0 [Ref-12], [Ref-19]。
   - **线膨胀系数**：可取 $10 \times 10^{-6} \text{ K}^{-1}$ [Ref-12], [Ref-19]。
2. **徐变变形（Creep）**
   - 徐变取决于环境湿度、构件尺寸、混凝土成分及加载龄期 [Ref-19]。
   - 在恒定压应力 $\sigma_c$ 作用下，最终徐变变形计算公式为：$\varepsilon_{cc}(\infty, t_0) = \varphi(\infty, t_0) \times (\sigma_c / E_c)$ [Ref-7], [Ref-12], [Ref-19]。
   - **非线性徐变**：当加载时（龄期 $t_0$）的压应力超过 $0.45 f_{ck}(t_0)$ 时，必须考虑非线性徐变效应 [Ref-12], [Ref-19]。
3. **收缩变形（Shrinkage）**
   - 包含**干燥收缩**（水分散失引起）和**自收缩**（水泥水化引起的宏观体积减小，高强混凝土中尤为显著） [Ref-19]。

### 三、 强度与变形的相互关系（应力-应变本构模型）
规范针对不同的计算目的，提供了多种强度与变形的关联模型：

1. **用于截面设计（ULS）的应力-应变关系**
   - **抛物线-矩形模型（Parabola-rectangle）**：由指数 $n$、达到最大强度的应变 $\varepsilon_{c2}$ 和极限应变 $\varepsilon_{cu2}$ 定义 [Ref-4], [Ref-11]。
   - **双线性模型（Bi-linear）**：作为等效或更保守的替代方案，由参数 $\varepsilon_{c3}$ 和 $\varepsilon_{cu3}$ 定义 [Ref-4], [Ref-11]。
   - **矩形应力块（Rectangular stress block）**：使用有效受压区高度系数 $\lambda$ 和有效强度系数 $\eta$ 进行简化计算 [Ref-4], [Ref-11]。**注意**：如果受压区宽度向极端受压纤维方向减小，$\eta f_{cd}$ 的值应再降低 10% [Ref-4], [Ref-11]。
2. **用于结构非线性分析的应力-应变关系**
   - 适用于短期单轴加载分析，使用峰值应力对应的应变 $\varepsilon_{c1}$ 和名义极限应变 $\varepsilon_{cu1}$ 来描述 [Ref-12]。
3. **约束混凝土（Confined Concrete）**
   - 侧向约束（如封闭箍筋）会改变有效的应力-应变关系，导致**更高的强度**和**更高的临界应变** [Ref-1], [Ref-9]。其修正后的特征强度和应变与极限状态下的有效侧向压应力 $\sigma_2 (= \sigma_3)$ 直接相关 [Ref-1], [Ref-9]。

### 四、 关键参数取值指南（基于 Table 3.1）
规范 Table 3.1 提供了从 C12/15 到15 到 C90/105 各强度等级的具体参数取值 [Ref-2]。核心参数随强度变化的趋势如下：
- **峰值应变**：$\varepsilon_{c1}$（分析用）和 $\varepsilon_{c2}$（设计用）随强度等级提高而增大（例如 $\varepsilon_{c2}$ 从 C50 以下的 2.0‰ 增至 C90 的 2.6‰） [Ref-2]。
- **极限应变**：$\varepsilon_{cu1}$、$\varepsilon_{cu2}$ 和 $\varepsilon_{cu3}$ 在 C50 以下通常取 3.5‰，但在高强混凝土（>C50）中随强度提高而**降低**（降至 C90 的 2.6‰） [Ref-2]。
- **抛物线指数 $n$**：在 C50 以下取 2.0，高强混凝土中逐渐减小至 1.4 [Ref-2]。

### 五、 适用条件与注意事项
1. **国家附录（National Annex）差异**：材料分项系数 $\gamma_c$、长期效应系数 $\alpha_{cc}$ 和 $\alpha_{ct}$ 的具体取值必须查阅项目所在国的国家附录 [Ref-12], [Ref-19]。
2. **骨料敏感性**：弹性模量 $E_{cm}$ 高度依赖于骨料类型。对于对变形敏感的结构（如大跨度或精密结构），规范建议通过受控试验实测变形属性，而非直接采用规范指示值 [Ref-12], [Ref-19]。
3. **轻骨料混凝土**：若使用轻骨料混凝土（密度 $\le 2200 \text{ kg/m}^3$），其弹性模量、徐变系数及极限应变等参数需根据规范第11章引入密度折减系数（如 $\eta_E = (\rho/2200)^2$）进行修正 [Ref-20]。
4. **早龄期强度**：若需计算 28 天之前的强度（如预应力传递或拆模阶段），需根据水泥类型和温度调整龄期进行计算，且此时 $\alpha_{cc}$ 等系数可能需乘以折减系数 $k_t$（推荐 0.85） [Ref-12], [Ref-14]。

---
**仍需补充的项目条件**：
为进行具体数值计算，您仍需明确：
1. 项目所在国家（以确定国家附录中的 $\gamma_c, \alpha_{cc}$ 等参数）。
2. 混凝土的具体骨料类型（以修正弹性模量）。
3. 构件所处的环境湿度及构件名义尺寸（用于查表计算徐变系数 $\varphi$ 和收缩应变）。

### 来源

- [1] EN1992-1-1_2004，页 36，条款 3.1.9: (1) Confinement of concrete results in a modification of the effective stress-strain relationship: higher strength and higher critical strains are achieved. The other basic material characteristics may be considered as unaffected for
- [2] EN1992-1-1 2004，页 28，条款 Table 3.1: Table 3.1 Strength and deformation characteristics for concrete <table><tr><td rowspan=1 colspan=15> Strength classes for concrete</td><td rowspan=1 colspan=1>Analytical relation/ Explanation</td></tr><tr><td rowspan=1 colspan=1>fck
- [3] DG EN1990，页 20，条款 : With regard to the definitions in clause 1.5 there are significant differences from usages in current national codes and standards (e.g. definitions in British codes), to improve precision of meaning and to facilitate translation into
- [4] EN1992-1-1_2004，页 34，条款 3.1.7: (1) For the design of cross-sections, the following stress-strain relationship may be used, see Figure 3.3 (compressive strain shown positive): (3.18) where: n is the exponent according to Table 3.1 $\varepsilon _ { \mathsf { C } 2 }$ is
- [5] EN1992-1-1_2004，页 2，条款 1.1.1, (1)P: 1. General 1.1 Scope 1.1.1 Scope of Eurocode 2 1.1.2 Scope of Part 1-1 of Eurocode 2 1.2 Normative references 1.2.1 General reference standards 1.2.2 Other reference standards 1.3 Assumptions 1.4 Distinction between principles and
- [6] EN1992-1-1_2004，页 16，条款 1.6: P Partial factor for actions associated with prestressing, $P$ Q Partial factor for variable actions, Q S Partial factor for reinforcing or prestressing steel S,fat Partial factor for reinforcing or prestressing steel under fatigue loading
- [7] EN1992-1-1 2004，页 30，条款 : $$ \varepsilon _ { \mathrm { c c } } ( \infty , t _ { 0 } ) = \varphi ( \infty , t _ { 0 } ) . ( \sigma _ { \mathrm { c } } / E _ { \mathrm { c } } ) $$
- [8] EN1992-1-1_2004，页 2，条款 : 1. General 1.1 Scope 1.1.1 Scope of Eurocode 2 1.1.2 Scope of Part 1-1 of Eurocode 2 1.2 Normative references 1.2.1 General reference standards 1.2.2 Other reference standards 1.3 Assumptions 1.4 Distinction between principles and

## 3. 有哪些因素会对混凝土的徐变与收缩产生影响?

- Excel 行号: 4
- 层级: Level 4 / 复杂场景与多参数耦合层

### 答案

根据欧洲规范 EN 1992-1-1 及其相关设计指南，影响混凝土徐变（Creep）与收缩（Shrinkage）的因素可归纳为共同影响因素、徐变特有因素、收缩特有因素以及针对轻骨料混凝土的特殊修正。

### 1. 共同影响因素
混凝土的徐变和收缩均受到以下基本因素的共同影响：
* **环境湿度**：周围环境的相对湿度直接决定了水分交换的速率 [Ref-1], [Ref-4], [Ref-12]。
* **构件尺寸与截面几何形状**：构件的尺寸（通常用截面面积与暴露于干燥环境的周长之比计算的名义尺寸 $h_0$ 来表示）影响水分散发和内部湿度的变化梯度 [Ref-1], [Ref-4], [Ref-6], [Ref-12]。
* **混凝土组成**：包括配合比设计等整体材料组成 [Ref-1], [Ref-4]。

### 2. 徐变（Creep）的特定影响因素
除上述共同因素外，徐变还显著受以下力学与时间因素影响：
* **加载时的混凝土成熟度（龄期）**：加载时混凝土的龄期越早，徐变越大 [Ref-1], [Ref-4], [Ref-12]。
* **荷载的持续时间与大小**：持荷时间越长，徐变发展越充分 [Ref-4], [Ref-12]。
* **材料特性**：混凝土强度、水泥类型以及骨料类型均会对徐变性能产生显著影响 [Ref-12]。
* **应力水平（非线性徐变前提）**：规范默认徐变与应力成正比（线性徐变）。但**当加载时（龄期 $t_0$）的混凝土压应力超过 $0.45 f_{ck}(t_0)$ 时**，必须考虑徐变的非线性发展，此时徐变系数需要乘以大于 1.0 的放大系数 [Ref-1], [Ref-4]。

### 3. 收缩（Shrinkage）的特定影响因素
收缩在规范中被明确划分为**干燥收缩**和**自收缩**两部分，两者的机理和主导因素不同：
* **干燥收缩**：是混凝土内部水分向周围空气散发的结果 [Ref-1]。其应变大小主要受环境湿度、构件名义尺寸以及干燥持续时间的控制 [Ref-6]。
* **自收缩**：是水泥水化后水泥基材料发生的宏观体积减小（不包含水分散失或温度变化引起的体积改变） [Ref-1]。
  * **水灰比**：自收缩与水灰比成反比 [Ref-1]。
  * **混凝土强度**：自收缩在**高强度混凝土**中尤为显著 [Ref-1]。其最终收缩值及随时间的发展系数与混凝土抗压强度等级（$f_{ck}$）直接正相关，强度等级越高，自收缩越大 [Ref-越大 [Ref-3]。

### 4. 轻骨料混凝土的特殊影响
对于轻骨料混凝土（密度 $\rho \le 2200 \text{ kg/m}^3$），其徐变和收缩行为还需考虑密度的修正：
* **徐变与干燥收缩**：轻骨料混凝土的徐变系数和最终干燥收缩值，需在普通混凝土计算值的基础上乘以与密度相关的修正系数（如徐变系数需乘以 $(\rho/2200)^2$） [Ref-6], [Ref-11]。
* **自收缩的降低**：如果使用的是饱水或部分饱水的轻骨料，骨料内部的水分可以向干燥的微观结构供水，这将导致轻骨料混凝土的自收缩值显著降低 [Ref-11]。

---
**工程师应用提示：**
1. 在进行正常使用极限状态（SLS）验算时，若构件存在较高的预压应力或长期压应力（如预应力构件），务必核查应力是否超过 $0.45 f_{ck}$ 阈值，以决定是否采用非线性徐变模型 [Ref-4]。
2. 规范提供的徐变和收缩预测模型及图表（如基于石英岩骨料的默认值）仅为指示性数据。若结构对变形极度敏感，或使用了特殊骨料（如石灰岩、玄武岩、砂岩等），建议通过受控试验确定实际材料的变形参数 [Ref-6], [Ref-13]。

### 来源

- [1] DG_EN1992-1-1__-1-2，页 64，条款 : The creep and shrinkage of concrete depend on a number of factors, including the ambient humidity, the dimensions of the element, the composition of the concrete and the age of concrete at the time of loading. The long-term values of the
- [2] DG_EN1992-1-1__-1-2，页 64，条款 Table 4.2: Table 4.2. Multipliers for non-linear creep
- [3] DG_EN1992-1-1__-1-2，页 64，条款 Table 4.6: Table 4.6. Autogenous shrinkage coefficients at different ages $\varepsilon _ { \mathrm { c a } } ( \infty ) \beta _ { \mathrm { a s } } ( t )$ (‰) <table><tr><td rowspan="2"></td><td colspan="11"> $f _ { \mathtt { c k } } \left( \mathsf {
- [4] EN1992-1-1 2004，页 30，条款 3.1.4, (1)P: (1)P Creep and shrinkage of the concrete depend on the ambient humidity, the dimensions of the element and the composition of the concrete. Creep is also influenced by the maturity of the concrete when the load is first applied and depends
- [5] EN1992-1-1_2004，页 30，条款 3.1.4, (1)P: (1)P Creep and shrinkage of the concrete depend on the ambient humidity, the dimensions of the element and the composition of the concrete. Creep is also influenced by the maturity of the concrete when the load is first applied and depends
- [6] DG_EN1992-1-1__-1-2，页 63，条款 : EN 1992-1-1 covers concrete of strength up to 90 MPa in normal-weight concrete and 80 MPa in lightweight concrete. It relies on EN 206-1 for the specification and production of concrete. In EN 1992-1-1 the compressive strength of concrete
- [7] DG_EN1992-1-1__-1-2，页 63，条款 : EN 1992-1-1 covers concrete of strength up to 90 MPa in normal-weight concrete and 80 MPa in lightweight concrete. It relies on EN 206-1 for the specification and production of concrete. In EN 1992-1-1 the compressive strength of concrete
- [8] DG_EN1992-1-1__-1-2，页 176，条款 : There are three factors to be considered in calculating the long term behaviour. These are: creep, shrinkage and, in cracked sections, reduction of the tensile stresses in the concrete in the tension zone due to the spreading with time of

## 4. 钢筋的主要特性有哪些?并给出相应总结。

- Excel 行号: 5
- 层级: Level 1 / 基础概念与符号体系层

### 答案

### 直接结论
根据欧洲规范 EN 1992-1-1，钢筋（reinforcing steel）的行为和性能由一系列力学、物理及工艺特性共同规定。主要包括屈服强度、抗拉强度、延性、粘结特性、弯曲性能、可焊性等，同时规范给出了弹性模量和密度的默认设计值。

---

### 依据与说明

#### 1. 力学与物理特性
*   **屈服强度（$f_{yk}$ 或 $f_{0,2k}$）与最大实际屈服强度（$f_{y,max}$）**：规范的设计和应用规则适用于特征屈服强度在 **400 MPa 至 600 MPa** 范围内的钢筋 [Ref-1], [Ref-4], [Ref-24]。
    *   *适用条件提醒*：具体国家允许使用的屈服强度上限值，必须查阅该国的**国家附录（National Annex）** [Ref-1], [Ref-4]。
*  。
*   **抗拉强度（$f_t$）**：定义为直接轴向拉伸下的特征最大荷载除以公称截面积 [Ref-4]。
*   **延性（Ductility）**：由最大荷载下的应变（$\varepsilon_{uk}$）和强屈比（$(f_t/f_{yk})_k$）共同定义 [Ref-1], [Ref-4], [Ref-22]。规范将延性划分为 **A、B、C 三个等级**；延性对利用结构塑性行为（如受弯构件的塑性铰转动能力）至关重要 [Ref-4], [Ref-22], [Ref-23]。
*   **疲劳强度（Fatigue strength）**：当结构需要验证疲劳强度时，需按照 EN 10080 标准进行验证 [Ref-4]。
*   **弹性模量（$E_s$）**：设计值可假定为 **200 GPa** [Ref-4]。
*   **密度**：平均值可假定为 **7850 kg/m³** [Ref-4]。

#### 2. 工艺与构造特性
*   **粘结特性（Bond characteristics）**：带肋钢筋的表面特征必须确保与混凝土有足够的粘结力，通常通过满足最小相对肋面积（$f_R$）的规范来保证 [Ref-1], [Ref-4]。
*   **弯曲性能（Bendability）**：钢筋必须具备足够的弯曲性能，以允许使用规范（Table 8.1）规定的最小弯芯直径，并允许进行重弯操作 [Ref-1], [Ref-4]。
*   **可焊性（Weldability）及焊接/剪切强度**：钢筋的可焊性需符合 EN 10080，焊接工艺需符合 EN ISO 17760 及规范允许的焊接方法（如闪光对焊、手工电弧焊等，详见规范 Table 3.4） [Ref-2], [Ref-4]。对于焊接网和桁架梁，还需满足特定的剪切和焊接强度要求 [Ref-1], [Ref-4]。
*   **截面尺寸和公差（Section sizes and tolerances）**：需符合相关产品标准（如 EN 10080） [Ref-1], [Ref-4]。

---

### 总结
钢筋的特性体系不仅涵盖了决定混凝土结构承载力与变形能力的**核心力学指标**（如屈服强度、延性、弹性模量），还严格规定了确保施工可行性与材料协同工作的**工艺及几何指标**（如粘结肋面积、弯曲与可焊性能）。

在实际工程应用中，工程师需特别注意以下前提与限制：
1.  **强度匹配与国家附录**：确保所选钢筋的特征屈服强度在 400~600 MPa 范围内，并务必核对项目所在国的国家附录对强度上限的具体规定。
2.  **延性与抗震要求**：在抗震设计或需要利用塑性内力重分布的区域，必须严格限制实际屈服强度上限（$f_{y,max}$，防止超强导致脆性破坏），并选择合适延性等级（A/B/C）的钢筋，以保证结构具有足够的塑性转动能力 [Ref-22], [Ref-24]。
3.  **材料验证时效**：所有钢筋特性的测试与验证程序均需遵循 EN 10080 标准；若现场操作（如加工、焊接）可能影响钢筋性能，必须在操作后重新验证其特性 [Ref-4], [Ref-5]。

---

### 依据位置
*   **特性列表及基本要求**：EN 1992-1-1 第 3.2.1 节、第 3.2.2 节 (1)P~(6)P [Ref-1], [Ref-4], [Ref-5], [Ref-7]
*   **物理参数（密度、弹性模量）及设计假设**：EN 1992-1-1 第 3.2.7 节 [Ref-4]
*   **焊接工艺要求**：EN 1992-1-1 第 3.2.5 节及 Table 3.4 [Ref-2], [Ref-4]
*   **延性与强度补充说明**：Designers' Guide to EN 1992-1-1 第 4.3.1 节、4.3.2 节 [Ref-22], [Ref-23], [Ref-24]

### 来源

- [1] EN1992-1-1_2004，页 37，条款 3.2.2, (1)P: (1)P The behaviour of reinforcing steel is specified by the following properties: \- yield strength $( f _ { \mathrm { y k } } \circ \mathsf { r } f _ { 0 , 2 \mathrm { k } } )$ \- maximum actual yield strength $( \pmb { f } _ { \mathsf {
- [2] EN1992-1-1 2004，页 39，条款 Table 3.4: Table 3.4: Permitted welding processes and examples of application <table><tr><td rowspan=1 colspan=1>Loading case</td><td rowspan=1 colspan=1>Welding method</td><td rowspan=1 colspan=1>Bars in tension1</td><td rowspan=1 colspan=1>Bars in
- [3] DG_EN1992-1-1__-1-2，页 142，条款 Table 8.1: Table 8.1. Neutral axis depths and moments of inertia for flanged beams (a) hf/d = 0.2 <table><tr><td rowspan="3"> $b _ { \mathrm { r } } / b$ </td><td colspan="9"></td></tr><tr><td colspan="2">1.0</td><td colspan="2">0.5</td><td
- [4] EN1992-1-1_2004，页 37，条款 3.2.1, (1)P: (1)P The following clauses give principles and rules for reinforcement which is in the form of bars, de-coiled rods, welded fabric and lattice girders. They do not apply to specially coated bars. (2)P The requirements for the properties of
- [5] EN1992-1-1_2004，页 37，条款 3.2.1, (1)P: (1)P The following clauses give principles and rules for reinforcement which is in the form of bars, de-coiled rods, welded fabric and lattice girders. They do not apply to specially coated bars. (2)P The requirements for the properties of
- [6] EN1992-1-1 2004，页 37，条款 3.2.1, (1)P: (1)P The following clauses give principles and rules for reinforcement which is in the form of bars, de-coiled rods, welded fabric and lattice girders. They do not apply to specially coated bars. (2)P The requirements for the properties of
- [7] EN1992-1-1 2004，页 37，条款 3.2.2, (1)P: (1)P The behaviour of reinforcing steel is specified by the following properties:
- [8] DG_EN1992-1-1__-1-2，页 7，条款 : Preface v Introduction v Layout of this guide v Chapter 1 Introduction 1 1.1. Scope 1 1.2. Layout 1 1.3. Related documents 2 1.4. Terminology 2 Chapter 2 Basis of design 5 2.1. Notation 5 2.2. General 5 2.3. Fundamental requirements 5 2.4.

## 5. 请问都有那些环境暴露等级?

- Excel 行号: 6
- 层级: Level 1 / 基础概念与符号体系层

### 答案

根据 EN 1992-1-1 规范，环境暴露等级（Exposure classes）根据环境条件（基于 EN 206-1）被划分为 **6个基本大类**，并进一步细分为多个子类，以定义侵蚀风险的严重程度 [Ref-3], [Ref-7]。

### 1. 详细分类及环境描述

**(1) 无钢筋锈蚀或混凝土腐蚀风险 (No risk of corrosion or attack)**
*   **X0**：对于无钢筋或预埋金属的混凝土：除冻融、磨损或化学腐蚀外的所有暴露环境；对于有钢筋或预埋金属的混凝土：非常干燥的环境（如：空气湿度极低的建筑物内部混凝土） [Ref-3]。

**(2) 碳化引起的钢筋锈蚀 (Corrosion induced by carbonation)**
*   **XC1**：干燥或永久湿润（如：空气湿度低的建筑物内部混凝土、永久淹没在水中的混凝土） [Ref-3]。
*   **XC2**：湿润，极少干燥（如：长期接触水的混凝土表面、许多基础） [Ref-3]。
*   **XC3**：中等湿度（如：空气湿度中等或高的建筑物内部混凝土、免受雨淋的外部混凝土） [Ref-3]。
*   **XC4**：干湿交替（如：接触水但不属于 XC2 类的混凝土表面） [Ref-3]。

**(3) 氯离子引起的钢筋锈蚀 (Corrosion induced by chlorides)**
*   **XD1**：中等湿度（如：暴露于空气中氯离子的混凝土表面） [Ref-3]。
*   **XD2**：湿润，极少干燥（如：游泳池、暴露于含氯工业水中的混凝土构件） [Ref-3]。
*   **XD3**：干湿交替（如：暴露于含氯喷雾的桥梁部件、路面、停车场楼板） [Ref-3]。

**(4) 海水中的氯离子引起的钢筋锈蚀 (Corrosion induced by chlorides from sea water)**
*   **XS1**：暴露于含盐空气中，但不直接接触海水（如：靠近海岸或海岸上的结构） [Ref-3]。
*   **XS2**：永久淹没（如：海洋结构物的部件） [Ref-3]。
*   **XS3**：潮汐区、飞溅区和喷雾区（如：海洋结构物的部件） [Ref-3]。

**(5) 冻融破坏 (Freeze/Thaw Attack)**
*   **XF1**：中等水饱和度，无除冰剂（如：暴露于雨水和冰冻的垂直混凝土表面） [Ref-3]。
*   **XF2**：中等水饱和度，有除冰剂（如：暴露于冰冻和空气中除冰剂的道路结构垂直混凝土表面） [Ref-3]。
*   **XF3**：高水饱和度，无除冰剂（如：暴露于雨水和冰冻的水平混凝土表面） [Ref-3]。
*   **XF4**：高水饱和度，有除冰剂或海水（如：暴露于除冰剂的道路和桥面、暴露于含除冰剂直接喷雾和冰冻的混凝土表面、暴露于冰冻的海洋结构物飞溅区） [Ref-3]。

**(6) 化学腐蚀 (Chemical attack)**
*   **XA1**：根据 EN 206-1 表2，轻微侵蚀性化学环境（如：天然土壤和地下水） [Ref-3]。
*   **XA2**：根据 EN 206-1 表2，中等侵蚀性化学环境（如：天然土壤和地下水） [Ref-3]。
*   **XA3**：根据 EN 206-1 表2，高度侵蚀性化学环境（如：天然土壤和地下水） [Ref-3]。

---

### 2. 适用条件与注意事项

*   **国家附录（National Annex）差异**：耐久性规定（如各暴露等级对应的指示性混凝土强度等级、最小保护层厚度等参数）在不同国家可能存在差异。具体设计时，必须查阅项目所在国的国家附录以获取当地法定参数 [Ref-6], [Ref-7]。
*   **轻骨料混凝土的特殊规定**：对于轻骨料混凝土，可使用与普通密度混凝土相同的指示性暴露等级 [Ref-5], [Ref-9]。但是，轻骨料混凝土的最小保护层厚度（$c_{min}$）必须在规范常规规定值的基础上**增加 5 mm** [Ref-13]。
*   **其他侵蚀形式**：除了上述表格中的分类，设计时还应考虑特定的侵蚀或间接作用，例如：化学攻击（酸或硫酸盐溶液、混凝土内含氯离子、碱骨料反应）和物理攻击（温度变化、磨损、水渗透） [Ref-1]。

---

### 3. 依据位置
*   **环境暴露等级分类表**等级分类表**：EN 1992-1-1:2004, Table 4.1 (页码 47-49) [Ref-3]
*   **环境条件基本原则**：EN 1992-1-1:2004, 4.2 (1)P - (3) (页码 47-49) [Ref-1]
*   **轻骨料混凝土规定**：EN 1992-1-1:2004, 11.4.1 及 11.4.2 (1)P (页码 189) [Ref-5], [Ref-13]
*   **国家附录及指示性强度说明**：EN 1992-1-1:2004, Annex E.1 (页码 210) [Ref-6]；指南说明 [Ref-7]

### 来源

- [1] EN1992-1-1_2004，页 47，条款 4.2, (1)P: (1)P Exposure conditions are chemical and physical conditions to which the structure is exposed in addition to the mechanical actions. (2) Environmental conditions are classified according to Table 4.1, based on EN 206-1. (3) In addition
- [2] EN1992-1-1 2004，页 24，条款 Table 2: Table 2.1N: Partial factors for materials for ultimate limit states <table><tr><td rowspan=1 colspan=1>Design situations</td><td rowspan=1 colspan=1>Yc for concrete</td><td rowspan=1 colspan=1>Ys for reinforcing steel</td><td rowspan=1
- [3] EN1992-1-1_2004，页 47，条款 Table 4.1: Table 4.1: Exposure classes related to environmental conditions in accordance with EN 206-1 <table><tr><td rowspan=1 colspan=1>Classdesignation</td><td rowspan=1 colspan=1>Description of the environment</td><td rowspan=1
- [4] DG_EN1992-1-1__-1-2，页 216，条款 Table 11.7: Table 11.7. Criteria for controlling cracking <table><tr><td rowspan="2">Exposure class</td><td rowspan="2">Unbonded tendons: quasi-permanent loads</td><td colspan="2">Bonded tendons</td></tr><tr><td>Frequent loads</td><td>Quasi-permanent
- [5] EN1992-1-1_2004，页 189，条款 11.4.1: (1) For lightweight aggregate concrete in Table 4.1 the same indicative exposure classes can be used as for normal density concrete.
- [6] EN1992-1-1_2004，页 210，条款 : (1) The choice of adequately durable concrete for corrosion protection of reinforcement and protection of concrete attack, requires consideration of the composition of concrete. This may result in a higher compressive strength of the
- [7] DG_EN1992-1-1__-1-2，页 189，条款 : There are two basic steps in designing for durability. These are: (1) Establish the aggressivity of the environment to which the member is exposed. This is analogous to establishing the design loading where the ultimate or serviceability
- [8] DG_EN1992-1-1__-1-2，页 211，条款 : In EN 1992-1-1, prestressed concrete is treated as part of a much wider material group known as reinforced concrete, which covers normal reinforced concrete through partially prestressed concrete to fully prestressed concrete. The

## 6. 保护层都与什么因素相关，该怎么计算?

- Excel 行号: 7
- 层级: Level 4 / 复杂场景与多参数耦合层

### 答案

根据欧洲规范 EN 1992-1-1，混凝土保护层的设计需要综合考虑粘结力传递、耐久性（防腐蚀）以及耐火性等因素。以下是保护层的相关因素及计算方法的详细说明：

### 1. 核心计算公式与定义
**混凝土保护层**是指最靠近混凝土表面的钢筋（包括箍筋和表面构造钢筋）表面与最近的混凝土表面之间的距离 [Ref-2, Ref-11]。
在图纸上必须标注的是**名义保护层（Nominal cover, $c_{nom}$）**，其计算公式为 [Ref-2, Ref-8, Ref-11]：
$$c_{nom} = c_{min} + \Delta c_{dev}$$
- **$c_{min}$**：最小保护层（Minimum cover）
- **$\Delta c_{dev}$**：设计时考虑的施工允许偏差（Allowance in design for deviation）

---

### 2. 最小保护层 ($c_{min}$) 的相关因素与计算
最小保护层 $c_{min}$ 必须同时满足**安全传递粘结力**、**保护钢筋免受腐蚀（耐久性）**以及**足够的耐火性**（依据 EN 1992-1-2）的要求 [Ref-9, Ref-11]。
计算时，应取满足“粘结要求”和“环境条件（耐久性）要求”两者中的**较大值** [Ref-9, Ref-11]：

#### (1) 基于粘结要求的最小保护层 ($c_{min,b}$)
为了保证粘结力的安全传递和混凝土的充分振捣，保护层不得小于 $c_{min,b}$ [Ref-9, Ref-11]：
- **普通钢筋**：通常与钢筋直径相关（具体查表 4.2）。
- **后张法预应力管道**：圆形管道为管道直径；矩形管道为较小尺寸或较大尺寸一半的较大值，且最大不超过 80 mm [Ref-6, Ref-9, Ref-11]。
- **先张法预应力筋**：钢绞线或光面钢丝为 1.5 倍直径；刻痕钢丝；刻痕钢丝为 2.5 倍直径 [Ref-6, Ref-9, Ref-11]。

#### (2) 基于环境条件（耐久性）的最小保护层 ($c_{min,dur}$)
该值主要取决于结构所处的**暴露等级（Exposure classes）**和**结构分类（Structural classes）** [Ref-9, Ref-11]。
环境条件计算中还需考虑以下修正参数 [Ref-9, Ref-11]：
- **$\Delta c_{dur,\gamma}$**：附加安全元素。
- **$\Delta c_{dur,st}$**：使用不锈钢时的保护层折减值。
- **$\Delta c_{dur,add}$**：使用附加保护措施时的保护层折减值。
*(注：普通钢筋和预应力钢的 $c_{min,dur}$ 推荐值分别见规范表 4.4N 和表 4.5N，但规范建议为预应力钢提供更大的保护层以降低腐蚀风险 [Ref-6, Ref-9, Ref-11]。)*

---

### 3. 施工允许偏差 ($\Delta c_{dev}$) 的相关因素与取值
$\Delta c_{dev}$ 是为了弥补施工过程中的负偏差而增加的余量 [Ref-1, Ref-5, Ref-7]。
- **常规推荐值**：10 mm [Ref-1, Ref-5, Ref-7]。
- **可折减的情况**（需查阅国家附录确认是否适用） [Ref-1, Ref-5, Ref-7]：
  - 若制造受质量保证体系控制，且监测包含保护层测量：可折减至 **5 mm ~ 10 mm**。
  - 若使用高精度测量设备监测并拒收不合格构件（如预制构件）：可折减至 **0 mm ~ 10 mm**。

---

### 4. 特殊工况下的保护层调整
当混凝土浇筑在**不平整表面**上时，必须增加最小保护层以允许更大的设计偏差 [Ref-1, Ref-5, Ref-7]：
- **在准备好的地基（含垫层）上浇筑**：最小保护层至少为 $k_1$（推荐值 **40 mm**） [Ref-1, Ref-5, Ref-7]。
- **直接在土壤上浇筑**：最小保护层至少为 $k_2$（推荐值 **75 mm**） [Ref-1, Ref-5, Ref-7]。
- **表面具有特殊特征**（如肋状饰面或裸露骨料）：也必须增加保护层以考虑表面的不平整度 [Ref-1, Ref-5, Ref-7]。

---

### ⚠️ 工程师应用提醒（国家附录与前提条件）
1. **国家附录（National Annex）优先**：上述提到的 $c_{min,dur}$ 具体数值、结构分类（推荐 S4）、偏差折减范围（$\Delta c_{dev}$）以及不平整表面系数（$k_1, k_2$）的**最终取值必须以项目所在国的国家附录为准** [Ref-1, Ref-5, Ref-7, Ref-9, Ref-11]。
2. **耐火设计**：若项目有严格的防火要求，保护层厚度还需满足 EN 1992-1-2 的耐火验算要求，此时 $c_{min}$ 可能需要进一步放大 [Ref-9, Ref-11]。
3. **图纸标注**：计算得出的名义保护层 $c_{nom}$ 必须直接用于结构计算，并明确标注在施工图纸上 [Ref-1, Ref-5, Ref-7]。

### 依据位置
- 保护层定义与名义保护层公式：EN 1992-1-1:2004, 4.4.1.1 (1)P, (2)P, 公式 4.1 [Ref-2, Ref-3, Ref-8, Ref-11]
- 最小保护层 $c_{min}$ 影响因素及参数：EN 1992-1-1:2004, 4.4.1.2 (1)P~(5) [Ref-9, Ref-11]
- 施工偏差 $\Delta c_{dev}$ 及不平整表面调整：EN 1992-1-1:2004, 4.4.1.3 (1)P~(4) [Ref-1, Ref-5, Ref-7]
- 预应力构件保护层特殊指南说明：DG_EN1992-1-1, Chapter 11 (Prestressed concrete) [Ref-6]

### 来源

- [1] EN1992-1-1_2004，页 52，条款 4.4.1.3, (1)P: (1)P To calculate the nominal cover, $c _ { \mathsf { n o m } } ,$ , an addition to the minimum cover shall be made in design to allow for the deviation $( \Delta c _ { \mathsf { d e v } } )$ . The required minimum cover shall be increased
- [2] EN1992-1-1_2004，页 49，条款 4.4.1.1, (1)P: (1)P The concrete cover is the distance between the surface of the reinforcement closest to the nearest concrete surface (including links and stirrups and surface reinforcement where relevant) and the nearest concrete surface. (2)P The
- [3] EN1992-1-1 2004，页 49，条款 4.4.1.1, (1)P: (1)P The concrete cover is the distance between the surface of the reinforcement closest to the nearest concrete surface (including links and stirrups and surface reinforcement where relevant) and the nearest concrete surface. (2)P The
- [4] DG_EN1992-1-1__-1-2，页 193，条款 : The main guidance on detailing is contained in Sections 8 and 9 of EN 1992-1-1. Cover requirements are in Section 4, under durability. The main aspects of detailing are concerned with anchoring bars carrying stress and lapping of
- [5] EN1992-1-1 2004，页 52，条款 4.4.1.3, (1)P: (1)P To calculate the nominal cover, $c _ { \mathsf { n o m } }$ , an addition to the minimum cover shall be made in design to allow for the deviation $( \Delta c _ { \mathsf { d e v } } )$ . The required minimum cover shall be increased
- [6] DG_EN1992-1-1__-1-2，页 211，条款 : In EN 1992-1-1, prestressed concrete is treated as part of a much wider material group known as reinforced concrete, which covers normal reinforced concrete through partially prestressed concrete to fully prestressed concrete. The
- [7] EN1992-1-1_2004，页 52，条款 4.4.1.3, (1)P: (1)P To calculate the nominal cover, $c _ { \mathsf { n o m } } ,$ , an addition to the minimum cover shall be made in design to allow for the deviation $( \Delta c _ { \mathsf { d e v } } )$ . The required minimum cover shall be increased
- [8] EN1992-1-1_2004，页 49，条款 : $$ c _ { \mathrm { n o m } } = c _ { \mathrm { m i n } } + \Delta c _ { \mathrm { d e v } }\tag{4.1} $$

## 7. 结构分析的目的是什么?

- Excel 行号: 8
- 层级: Level 1 / 基础概念与符号体系层

### 答案

### 直接结论
结构分析的主要目的是确定结构整体或局部的**作用效应（Action effects）分布**（如内力、弯矩，或应力、应变和位移），并以此为基础**验证结构的整体稳定性**以及**评估其在各种极限状态下的可靠性**。

### 依据与详细说明

1. **确定作用效应分布**
   结构分析旨在确立整个结构或其某一部分的内力（internal forces）和弯矩（moments）分布，或者应力（stresses）、应变（strains）和位移（displacements）的分布 [Ref-1]。在此基础上，可进一步计算截面的曲率、转角和位移等参数 [Ref-2]。

2. **验证整体稳定性与极限状态可靠性**
   通过结构建模和分析确定的截面、节点或构件中的作用效应，可用于验证建筑和土木工程结构在各种极限状态（如承载能力极限状态和正常使用极限状态）下的整体稳定性和可靠性 [Ref-2], [Ref-8]。

3. **为截面抗力验证提供基础**
   - **常规情况**：在大多数正常设计中，分析主要用于确定内力和弯矩的分布，截面的完整验证或抗力证明正是基于这些作用效应来进行的 [Ref-1]。
   - **特殊情况**：对于某些特定构件，所采用的分析方法（例如有限元分析）可能直接输出应力、应变和位移，而不是内力和弯矩。在这种情况下，必须采用特殊方法来利用这些结果以获得适当的截面验证 [Ref-1]。

4. **局部分析的补充**
   除了整体分析外，在必要时（例如线性应变分布假设不成立的区域，如支座附近、集中荷载作用处、梁柱节点、锚固区或截面突变处）还应进行附加的局部分析（Local analysis） [Ref-1]。

### 依据位置
- **[Ref-1]** EN 1992-1-1:2004, 条款 5.1.1 (1)P 及其 Note, 第 53 页
- **[Ref-2]** Designers' Guide to EN 1992-1-1, 章节 3.1 Introduction, 第 33 页
- **[Ref-8]** Designers' Guide to EN 1990, 章节 5 (Structural analysis and design assisted by testing) 概述, 第 67 页

### 来源

- [1] EN1992-1-1_2004，页 53，条款 5.1.1, (1)P: (1)P The purpose of structural analysis is to establish the distribution of either internal forces and moments, or stresses, strains and displacements, over the whole or part of a structure. Additional local analysis shall be carried out
- [2] DG_EN1992-1-1__-1-2，页 33，条款 : The purpose of analysis is the verification of overall stability and establishment of action effects, i.e. the distribution of internal forces and moments. In turn, this will enable the calculation of stresses, strains, curvature, rotation
- [3] EN1992-1-1 2004，页 53，条款 5.1.1, (1)P: (1)P The purpose of structural analysis is to establish the distribution of either internal forces and moments, or stresses, strains and displacements, over the whole or part of a structure. Additional local analysis shall be carried out
- [4] DG_EN1992-1-1__-1-2，页 33，条款 : In the analysis of the structure, the designer should consider the effects of the realistic combinations of permanent and variable actions. Within each set of combinations (e.g. dead and imposed loads) a number of different arrangements of
- [5] EN1992-1-1_2004，页 218，条款 : (1) For the purpose of this section flat slabs may be of uniform thickness or they may incorporate drops (thickenings over columns). (2) Flat slabs should be analysed using a proven method of analysis, such as grillage (in which the plate
- [6] DG EN1990，页 69，条款 : In the previous version of the Eurocode (ENV 1991-1), an increase of more than $1 0 \%$ in the effects of actions was proposed, but it was recognised that such a value depends on the particular construction and/or its structural material.
- [7] DG EN1990，页 67，条款 : This chapter is concerned with the modelling of building and civil engineering structures for the purpose of determining action effects and resistances. The material described in this chapter is covered in Section 5 of EN 1990, in the
- [8] DG_EN1990，页 67，条款 5.1.1, 5.1.2: The Principles and Application Rules presented in Section 5 of EN 1990 primarily deal with the modelling of structures. Action effects in cross-sections, joints or members determined through structural modelling and analysis can be used to

## 8. 在哪些部位当线性应变分布的假设不成立时，可能需要进行局部分析?

- Excel 行号: 9
- 层级: Level 2 / 构件极限状态计算层

### 答案

根据欧洲规范 EN 1992-1-1 及其相关设计指南，当线性应变分布假设（即平截面假定）不成立时，除了整体分析外，还需要在以下部位进行额外的局部分析：

### 需要进行局部分析的部位
1. **支座附近**（in the vicinity of supports）[Ref-1]。
2. **集中荷载作用处及其邻近区域**（local to concentrated loads / locations adjacent to concentrated loads）[Ref-1], [Ref-3]。
3. **梁柱节点/交接处**（in beam-column intersections / junctions）[Ref-1], [Ref-3]。
4. **锚固区**（in anchorage zones）[Ref-1], [Ref-3]。
5. **截面突变处**，包括大洞口附近（at changes in cross section / members with significant changes in cross-section, including the vicinity of large holes）[Ref-1], [Ref-3]。
6. **存在平面应力状态的区域**（plain stress / in-plane stress fields）[Ref-1], [Ref-7]。
7. **短构件**（如深梁、牛腿等，因其内部变形复杂，平截面假定不再适用）[Ref-5]。

### 依据与说明
- **分析要求**：结构分析的目的通常是确定内力分布，但在上述几何或受力不连续的区域，线性应变分布假设失效，必须开展局部分析以准确评估应力、应变和位移分布 [Ref-1]。
- **推荐分析方法**：对于这些非线性应变分布区域，规范推荐采用**拉压杆模型（Strut-and-tie models）** 等基于塑性下限定理的方法进行局部分析和承载力验证 [Ref-3], [Ref-7], [Ref-18]。此外，对于平面应力场，也可参考规范附录 F（Annex F）提供的简化方法来确定配筋 [Ref-1]。

### 依据位置
- EN 1992-1-1:2004, 条款 5.1.1(2) [Ref-1]
- EN 1992-1-1:2004, 条款 6.5.1(1)P [Ref-7]
- EN 1992-1-1:2004, 条款 5.6.4 [Ref-18]
- DG_EN1992-1-1 指南, 章节 3.1 Introduction [Ref-3]
- DG_EN1992-1-1 指南, 章节 5.1.2 Assumptions relating to the strains at the ultimate limit state [Ref-5]

### 来源

- [1] EN1992-1-1_2004，页 53，条款 5.1.1, (1)P: (1)P The purpose of structural analysis is to establish the distribution of either internal forces and moments, or stresses, strains and displacements, over the whole or part of a structure. Additional local analysis shall be carried out
- [2] EN1992-1-1_2004，页 53，条款 5.1.1, (1)P: (1)P The purpose of structural analysis is to establish the distribution of either internal forces and moments, or stresses, strains and displacements, over the whole or part of a structure. Additional local analysis shall be carried out
- [3] DG_EN1992-1-1__-1-2，页 33，条款 : The purpose of analysis is the verification of overall stability and establishment of action effects, i.e. the distribution of internal forces and moments. In turn, this will enable the calculation of stresses, strains, curvature, rotation
- [4] DG_EN1992-1-1__-1-2，页 48，条款 : Strut-and-tie models utilize the lower-bound theorem of plasticity, which can be summarized as follows: for a structure under a given system of external loads, if a stress distribution throughout the structure can be found such that (1)
- [5] DG_EN1992-1-1__-1-2，页 75，条款 : The basic assumptions here are that plane sections remain plane and that the strain in reinforcement is the same as the strain in the concrete at the same level. These assumptions are universally accepted for the design of members
- [6] EN1992-1-1 2004，页 53，条款 5.1.1, (1)P: (1)P The purpose of structural analysis is to establish the distribution of either internal forces and moments, or stresses, strains and displacements, over the whole or part of a structure. Additional local analysis shall be carried out
- [7] EN1992-1-1_2004，页 107，条款 6.5.1, (1)P: (1)P Where a non-linear strain distribution exists (e.g. supports, near concentrated loads or plain stress) strut-and-tie models may be used (see also 5.6.4).
- [8] EN1992-1-1 2004，页 107，条款 6.5.1, (1)P: (1)P Where a non-linear strain distribution exists (e.g. supports, near concentrated loads or plain stress) strut-and-tie models may be used (see also 5.6.4).

## 9. 根据性质和功能，结构构件包括哪些类型?

- Excel 行号: 10
- 层级: Level 1 / 基础概念与符号体系层

### 答案

根据欧洲规范 EN 1992-1-1 的规定，基于性质和功能，结构构件的分类及建筑中常见构件的具体界定如下：

### 1. 结构构件的基本分类
考虑结构构件的性质和功能，结构元素（构件）主要分类为：**梁（beams）、柱（columns）、板（slabs）、墙（walls）、平板（plates）、拱（arches）、壳（shells）** 等 [Ref-1]。规范也为这些常见构件及其组合结构的分析提供了相关规则 [Ref-1]。

### 2. 建筑中常见构件的具体界定条件
对于建筑结构（buildings），规范根据几何尺寸比例对部分常见构件的类型界定给出了明确的划分条件 [Ref-1]：
* **梁（Beam）与深梁（Deep beam）**：当构件的跨度不小于其截面总高度的 3 倍时，视为梁；否则应将其视为深梁 [Ref-1]。
* **板（Slab）**：当构件的最小板块尺寸不小于板总厚度的 5 倍时，视为板 [Ref-1]。
* **柱（Column）与墙（Wall）**：当构件的截面高度不超过其宽度的 4 倍，且高度至少为截面高度的 3 倍时，视为柱；否则应将其视为墙 [Ref-1]。

### 依据位置
* **文档名**：EN 1992-1-1:2004 (Eurocode 2: Design of concrete structures - Part 1-1)
* **条款/章节**：5.3.1 Structural models for overall analysis, 条款 (1)P, (3), (4), ( (4), (7)
* **页码**：57
* **对应证据片段**：[Ref-1], [Ref-2], [Ref-12]

### 来源

- [1] EN1992-1-1 2004，页 57，条款 5.3.1, (1)P: (1)P The elements of a structure are classified, by consideration of their nature and function, as beams, columns, slabs, walls, plates, arches, shells etc. Rules are provided for the analysis of the commoner of these elements and of
- [2] EN1992-1-1_2004，页 57，条款 5.3.1, (1)P: (1)P The elements of a structure are classified, by consideration of their nature and function, as beams, columns, slabs, walls, plates, arches, shells etc. Rules are provided for the analysis of the commoner of these elements and of
- [3] DG_EN1992-1-1__-1-2，页 193，条款 : The main guidance on detailing is contained in Sections 8 and 9 of EN 1992-1-1. Cover requirements are in Section 4, under durability. The main aspects of detailing are concerned with anchoring bars carrying stress and lapping of
- [4] DG_EN1992-1-1__-1-2，页 230，条款 : Section 5 of EN 1992-1-2 sets out minimum dimensions and axis distances (cover plus half the diameter of the reinforcement bar) for different types of structural element for fire exposure periods of 30, 60, 90, 120, 180 and 240 min. Some
- [5] EN1992-1-1 2004，页 64，条款 5.8.1: Biaxial bending: simultaneous bending about two principal axes Braced members or systems: structural members or subsystems, which in analysis and design are assumed not to contribute to the overall horizontal stability of a structure
- [6] DG EN1990，页 46，条款 : Examples of classification for most common types of action are given in Table 4.1. However, this classification corresponds to typical conditions only, and may not apply in certain specific cases. Depending on site location and the actual
- [7] EN1992-1-1 2004，页 172，条款 10.1.1: Precast element: element manufactured in a factory or a place other than the final position in the structure, protected from adverse weather conditions Precast product: precast element manufactured in compliance with a specific CEN
- [8] DG_EN1990，页 25，条款 2.1.4: 3 ‘Selecting a structural form and design that survive adequately the accidental removal of an individual element or a limited part of the structure or the occurrence of acceptable localised damage.’ For this measure: – each load-bearing

## 10. 什么是单向板?

- Excel 行号: 11
- 层级: Level 1 / 基础概念与符号体系层

### 答案

### 直接结论
在主要承受均布荷载的前提下，满足特定边界支撑条件或长宽比条件的混凝土板可被判定为**单向板（one-way spanning slab）**。

### 依据与说明
根据欧洲规范 EN 1992-1-1 的规定，承受主要均布荷载的板若满足以下任一条件，可视为单向板 [Ref-1]：
1. 具有两个自由（无支撑）且大致平行的边缘 [Ref-1]。
2. 它是四边支撑的大致矩形板的中心部分，且长跨与短跨之比大于 2 [Ref-1]。

**指南补充说明（防火设计）：**
在结构防火设计的相关指南中明确指出，双向板的设计数据仅适用于四边均有支撑的板；如果不满足四边支撑的条件，该板应按单向板进行处理 [Ref-3]。

### 依据位置
- **[Ref-1]** EN1992-1-1 2004, 章节 5.3.1 (Structural models for overall analysis), 条款 (5), 页码 57
- **[Ref-3]** DG_EN1992-1-1__-1-2 (指南), 章节 Structural fire design > Slabs, 页码 232

### 来源

- [1] EN1992-1-1 2004，页 57，条款 5.3.1, (1)P: (1)P The elements of a structure are classified, by consideration of their nature and function, as beams, columns, slabs, walls, plates, arches, shells etc. Rules are provided for the analysis of the commoner of these elements and of
- [2] EN1992-1-1 2004，页 62，条款 5.6.3: (1) The simplified procedure for continuous beams and continuous one way spanning slabs is based on the rotation capacity of beam/slab zones over a length of approximately 1,2 times the depth of section. It is assumed that these zones
- [3] DG_EN1992-1-1__-1-2，页 232，条款 : The data for two-way spanning slabs are applicable only to slabs supported on all four edges. If this is not met, the slab should be treated as one-way spanning. The thickness of the slab for continuous slabs is the same as for simply
- [4] EN1992-1-1_2004，页 127，条款 Table 7: Table 7.4N: Basic ratios of span/effective depth for reinforced concrete members without axial compression <table><tr><td> Structural System</td><td>K</td><td>Concrete highly stressed $\rho = 1 { , } 5 \%$ </td><td>Concrete lightly
- [5] DG_EN1992-1-1__-1-2，页 55，条款 : Flat slab structures are defined as slabs (solid or coffered) supported on point supports. Unlike two-way spanning slabs on line supports, flat slabs can fail by yield lines in either of the two orthogonal directions (Fig. 3.24). For this
- [6] DG_EN1992-1-1__-1-2，页 55，条款 : Flat slab structures are defined as slabs (solid or coffered) supported on point supports. Unlike two-way spanning slabs on line supports, flat slabs can fail by yield lines in either of the two orthogonal directions (Fig. 3.24). For this
- [7] EN1992-1-1 2004，页 158，条款 9.3: (1) This section applies to one-way and two-way solid slabs for which $b$ and $I _ { \mathsf { e f f } }$ are not less than $5 h$ (see 5.3.1).
- [8] EN1992-1-1_2004，页 62，条款 5.6.3: (1) The simplified procedure for continuous beams and continuous one way spanning slabs is based on the rotation capacity of beam/slab zones over a length of approximately 1,2 times the depth of section. It is assumed that these zones

## 11. 欧标的截面计算的基本假设前提是什么？

- Excel 行号: 12
- 层级: Level 1 / 基础概念与符号体系层

### 答案

根据欧洲规范（以混凝土结构 EN 1992-1-1 和结构设计基础 EN 1990 为例），截面计算的基本假设前提可分为**截面力学计算假定**和**欧标体系通用前提假定**。

### 一、 截面力学计算的基本假设（承载能力极限状态）
在确定钢筋混凝土或预应力混凝土截面（受弯或压弯）的极限承载力时，规范规定了以下核心力学假设 [Ref-2, Ref-10]：
1. **平截面假定**：构件在加载变形前后，截面保持平面 [Ref-2, Ref-10]。
2. **应变协调假定**：有粘结的普通钢筋或有粘结的预应力筋（无论受拉还是受压），其应变与周围同一位置的混凝土应变相同 [Ref-2, Ref-10]。对于预应力截面，需考虑钢筋在粘结前的初始应变，粘结后其应变变化量假定与混凝土相同 [Ref-3, Ref-13]。
3. **忽略混凝土抗拉强度**：在截面承载力计算中，不考虑混凝土的抗拉作用 [Ref-2, Ref-10]。
4. **材料本构关系**：
   - 受压混凝土的应力由规范第 3.1.7 节给出的设计应力-应变关系推导 [Ref-2, Ref-10]。
   - 钢筋或预应力钢的应力由规范第 3.2 节和第 3.3 节的设计曲线推导 [Ref-2, Ref-10]。
5. **预应力初始应变**：在评估预应力筋的应力时，必须计入其初始应变 [Ref-2, Ref-10]。
6. **应变限值**：混凝土的受压应变需限制在 $\varepsilon_{cu2}$ 或 $\varepsilon_{cu3}$（取决于所选的应力-应变图）；钢筋和预应力钢的应变需限制在 $\varepsilon_{ud}$（如适用） [Ref-2, Ref-10]。

### 二、 预应力钢材的特定截面设计假设
针对预应力钢材的截面设计，规范允许在应力-应变关系中采用以下两种假设之一 [Ref-1, Ref-4]：
1. **带应变限制的倾斜分支**：设定极限应变 $\varepsilon_{ud}$（推荐值为 $0.9\varepsilon_{uk}$，若未知则推荐取 $0.02$） [Ref-1, Ref-4]。
2. **无应变限制的水平顶部分支**：即达到屈服后应力保持水平，不限制最大应变 [Ref-1, Ref-4]。

### 三、 适用范围与限制条件（重要提醒）
根据规范及设计指南的补充说明，上述力学假设并非在所有情况下都严格成立，工程师需注意以下限制 [Ref-3, Ref-7, Ref-13]：
1. **局部不准确性**：由于局部粘结滑移和复杂的内部变形，平截面和应变完全协调在微观局部并不严格成立，但在平均意义上对常规构件的设计足够准确 [Ref-3, Ref-7, Ref-13]。
2. **不适用于短构件**：对于深梁（deep beams）、牛腿（corbels）等短构件，平截面假定失效，不能使用该章节的截面计算规定，而应按规范第 6.5 节（不连续区域/拉压杆模型）进行设计和配筋 [Ref-2, Ref-2, Ref-3, Ref-10, Ref-13]。
3. **不适用于无粘结预应力筋**：应变协调假定对无粘结预应力筋无效。无粘结预应力构件需按规范第 5.10.8 节的专门规定进行设计 [Ref-2, Ref-3, Ref-10, Ref-13]。对于体外预应力筋，假定两个接触点（锚具或转向块）之间的预应力筋应变保持恒定 [Ref-2, Ref-10]。

### 四、 欧标体系的通用基本假设（EN 1990）
除了力学计算假定，采用欧标进行任何设计（包括截面计算）均必须满足 EN 1990 第 1.3 节规定的通用前提假设 [Ref-8, Ref-9]：
1. 结构系统的选择和设计由具备适当资质和经验的人员完成 [Ref-8, Ref-9]。
2. 施工由具备适当技能和经验的人员执行，并在设计、工厂和现场提供充分的监督与质量控制 [Ref-8, Ref-9]。
3. 建筑材料和产品严格按照欧标及相关产品规范使用 [Ref-8, Ref-9]。
4. 结构将得到充分的维护，并严格按照设计假设（如不超载）进行使用 [Ref-8, Ref-9]。

---
**依据位置：**
- [Ref-1] EN 1992-1-1:2004, 条款 3.3.6 (7), 页码 44
- [Ref-2] EN 1992-1-1:2004, 条款 6.1 (1)P, (2)P, (3)P, (7), (8), 页码 83
- [Ref-3] Designers' Guide to EN 1992-1-1, 章节 5.1.2, 页码 75
- [Ref-4] EN 1992-1-1:2004, 条款 3.3.6 (7), 页码 44-45
- [Ref-7] Designers' Guide to EN 1992-1-1, 章节 Derivation of stress block parameters, 页码 75
- [Ref-8] Designers' Guide to EN 1990, 章节 1.3 Assumptions, 页码 18-19
- [Ref-9] Designers' Guide to EN 1990, 章节 1.3 Assumptions, 页码 18-19
- [Ref-10] EN 1992-1-1:2004, 条款 6.1 (1)P, (2)P, (3)P, (7), (8), 页码 83-84
- [Ref-13] Designers' Guide to EN 1992-1-1, 章节 Design of sections for bending and axial force, 页码 75

### 来源

- [1] EN1992-1-1_2004，页 44，条款 3.3.6, (1)P: (1)P Structural analysis is performed on the basis of the nominal cross-section area of the prestressing steel and the characteristic values $f _ { \mathsf { p 0 } , 1 \mathsf { k } } , f _ { \mathsf { p k } }$ and ${ \pmb { \varepsilon }
- [2] EN1992-1-1_2004，页 83，条款 6.1, (1)P: (1)P This section applies to undisturbed regions of beams, slabs and similar types of members for which sections remain approximately plane before and after loading. The discontinuity regions of beams and other members in which plane
- [3] DG_EN1992-1-1__-1-2，页 75，条款 : The basic assumptions here are that plane sections remain plane and that the strain in reinforcement is the same as the strain in the concrete at the same level. These assumptions are universally accepted for the design of members
- [4] EN1992-1-1 2004，页 44，条款 3.3.6, (1)P: (1)P Structural analysis is performed on the basis of the nominal cross-section area of the prestressing steel and the characteristic values $f _ { \mathsf { p 0 } , 1 \mathsf { k } } , f _ { \mathsf { p k } }$ and ${ \pmb { \varepsilon }
- [5] DG_EN1992-1-1__-1-2，页 232，条款 : This method requires knowledge of the temperature distribution across the cross-section of the member. EN 1992-1-2 provides such profiles for slabs, beams and columns in Annex A for standard time-temperature relationships. The method may
- [6] EN1992-1-1_2004，页 2，条款 1.1.1, (1)P: 1. General 1.1 Scope 1.1.1 Scope of Eurocode 2 1.1.2 Scope of Part 1-1 of Eurocode 2 1.2 Normative references 1.2.1 General reference standards 1.2.2 Other reference standards 1.3 Assumptions 1.4 Distinction between principles and
- [7] DG_EN1992-1-1__-1-2，页 75，条款 : The basic assumptions here are that plane sections remain plane and that the strain in reinforcement is the same as the strain in the concrete at the same level. These assumptions are universally accepted for the design of members
- [8] DG_EN1990，页 18，条款 : ‘A design which employs the Principles and Application Rules is deemed to meet the requirements of EN 1990, provided the following assumptions are satisfied.’ The assumptions that need to be satisfied (clause 1.3(2)) are: ‘The choice of

## 12. 混凝土受压区应变-应力分布假设是什么？

- Excel 行号: 13
- 层级: Level 1 / 基础概念与符号体系层

### 答案

### 直接结论
在混凝土截面设计（如受弯或压弯构件）中，混凝土受压区的应变-应力分布假设主要基于**平截面假定**，并允许采用三种理想化的应力-应变关系模型：**抛物线-矩形分布**、**双线性分布**或**矩形应力块分布**。

---

### 一、 截面设计的基本前提假设
在确定钢筋混凝土或预应力混凝土截面的极限承载力时，必须遵循以下基本假设 [Ref-3, Ref-6]：
1. **平截面假定**：变形前垂直于轴线的截面，在受力变形后仍保持平面 [Ref-3, Ref-6]。
2. **应变协调**：粘结钢筋或粘结预应力筋的应变（无论受拉或受压）与周围混凝土的应变相同 [Ref-3, Ref-6]。
3. **忽略抗拉强度**：计算中忽略混凝土的抗拉强度 [Ref-3, Ref-6]。
4. **极限应变限制**：混凝土的极限压应变必须限制在 $\varepsilon_{cu2}$ 或 $\varepsilon_{cu3}$，具体限值取决于所采用的应力-应变模型 [Ref-3, Ref-6]。

---

### 二、 三种受压区应力-应变分布模型
根据规范第 3.1.7 节，截面设计可采用以下三种受压区应力-应变关系 [Ref-1, Ref-4]：

#### 1. 抛物线-矩形分布（Parabola-rectangle diagram）
这是规范给出的标准设计模型 [Ref-10, Ref-11]。
* **参数定义**：曲线段由指数 $n$ 控制，达到最大强度时的应变为 $\varepsilon_{c2}$，极限应变为 $\varepsilon_{cu2}$ [Ref-1, Ref-4]。
* **常规混凝土（$f_{ck} \le 50\text{ MPa}$）**：$n = 2.0$（即标准抛物线），$\varepsilon_{c2} = 2.0\text{‰}$，$\varepsilon_{cu2} = 3.5\text{‰}$ [Ref-2]。
* **高强混凝土（$f_{ck} > 50\text{ MPa}$）**：由于高强混凝土表现出更脆的特性，指数 $n$ 会从 2.0 逐渐减小至 1.4，此时曲线段不再是严格的抛物线，且极限应变 $\varepsilon_{cu2}$ 也会相应降低 [Ref-2, Ref-11]。

#### 2. 双线性分布（Bi-linear stress-strain relation）
若证明其等效于或比抛物线-矩形模型更保守，则可使用双线性简化模型 [Ref-1, Ref-4]。
* **参数定义**：关键参数为达到最大强度的应变 $\varepsilon_{c3}$ 和极限应变 $\varepsilon_{cu3}$ [Ref-1, Ref-4]。
* **常规混凝土（$f_{ck} \le 50\text{ MPa}$）**：$\varepsilon_{c3} = 1.75\text{‰}$，$\varepsilon_{cu3} = 3.5\text{‰}$ [Ref-2]。

#### 3. 矩形应力分布（Rectangular stress distribution）
为简化计算，可假设受压区应力呈矩形分布 [Ref-1, Ref-4]。
* **参数定义**：引入**有效受压区高度系数 $\lambda$** 和**有效强度系数 $\eta$** 来定义矩形应力块 [Ref-1, Ref-4]。
* **常规混凝土（$f_{ck} \le 50\text{ MPa}$）**：$\lambda = 0.8$，$\eta = 1.0$ [Ref-10, Ref-12]。
* **⚠️ 适用条件限制**：如果受压区宽度向极端受压纤维方向逐渐减小（例如三角形截面受压），则有效强度值 $\eta f_{cd}$ 必须**折减 10%** [Ref-1, Ref-4]。

---

### 三、 特殊情况：约束混凝土（Confined混凝土（Confined concrete）
如果混凝土受到有效的横向约束（如通过封闭箍筋或交叉拉筋），其应力-应变关系会发生改变，表现为**更高的抗压强度和更大的临界应变** [Ref-5, Ref-8]。
* 在缺乏精确数据时，可采用规范第 3.1.9 节提供的约束混凝土应力-应变关系模型 [Ref-5, Ref-8]。
* 其强度和应变参数会根据极限状态下的有效侧向压应力 $\sigma_2$ 进行放大计算 [Ref-5, Ref-8]。

---

### 四、 依据位置
* **基本前提假设**：EN 1992-1-1 第 6.1 节 (2)P [Ref-3, Ref-6]
* **应力-应变模型定义**：EN 1992-1-1 第 3.1.7 节 [Ref-1, Ref-4]
* **应变参数取值**：EN 1992-1-1 表 3.1 (Table 3.1) [Ref-2]
* **约束混凝土修正**：EN 1992-1-1 第 3.1.9 节 [Ref-5, Ref-8]
* **指南补充说明（矩形块参数及高强混凝土特性）**：DG_EN1992-1-1 第 4.1.5 节、第 5.1.1 节 [Ref-10, Ref-11, Ref-12]

### 来源

- [1] EN1992-1-1_2004，页 34，条款 3.1.7: (1) For the design of cross-sections, the following stress-strain relationship may be used, see Figure 3.3 (compressive strain shown positive): (3.18) where: n is the exponent according to Table 3.1 $\varepsilon _ { \mathsf { C } 2 }$ is
- [2] EN1992-1-1 2004，页 28，条款 Table 3.1: Table 3.1 Strength and deformation characteristics for concrete <table><tr><td rowspan=1 colspan=15> Strength classes for concrete</td><td rowspan=1 colspan=1>Analytical relation/ Explanation</td></tr><tr><td rowspan=1 colspan=1>fck
- [3] EN1992-1-1_2004，页 83，条款 6.1, (1)P: (1)P This section applies to undisturbed regions of beams, slabs and similar types of members for which sections remain approximately plane before and after loading. The discontinuity regions of beams and other members in which plane
- [4] EN1992-1-1 2004，页 34，条款 3.1.7: (1) For the design of cross-sections, the following stress-strain relationship may be used, see Figure 3.3 (compressive strain shown positive): where: $n$ is the exponent according to Table 3.1 $\varepsilon _ { \mathsf { C } 2 }$ is the
- [5] EN1992-1-1_2004，页 36，条款 3.1.9: (1) Confinement of concrete results in a modification of the effective stress-strain relationship: higher strength and higher critical strains are achieved. The other basic material characteristics may be considered as unaffected for
- [6] EN1992-1-1 2004，页 83，条款 6.1, (1)P: (1)P This section applies to undisturbed regions of beams, slabs and similar types of members for which sections remain approximately plane before and after loading. The discontinuity regions of beams and other members in which plane
- [7] EN1992-1-1_2004，页 107，条款 6.5.1, (1)P: (1)P Where a non-linear strain distribution exists (e.g. supports, near concentrated loads or plain stress) strut-and-tie models may be used (see also 5.6.4). (1) The design strength for a concrete strut in a region with transverse
- [8] EN1992-1-1 2004，页 36，条款 3.1.9: (1) Confinement of concrete results in a modification of the effective stress-strain relationship: higher strength and higher critical strains are achieved. The other basic material characteristics may be considered as unaffected for

## 13. 混凝土压碎应变限值是多少？

- Excel 行号: 14
- 层级: Level 1 / 基础概念与符号体系层

### 答案

根据欧洲规范 EN 1992-1-1 的规定，混凝土的压碎应变（极限压应变）限值取决于截面设计时所采用的应力-应变关系模型以及构件的受力状态。

### 直接结论
混凝土的极限压应变限值主要取 **$\varepsilonvarepsilon_{cu2}$**（对应抛物线-矩形应力图）或 **$\varepsilon_{cu3}$**（对应双线性应力图），具体数值需根据混凝土强度等级查阅规范原文的 **Table 3.1**。对于近似轴心受压区域，限值应取峰值应力对应的应变 **$\varepsilon_{c2}$** 或 **$\varepsilon_{c3}$**。

### 依据与说明
1. **一般受弯或压弯构件**
   在确定钢筋混凝土或预应力混凝土截面的极限抗弯承载力时，混凝土的压应变必须限制为 $\varepsilon_{cu2}$ 或 $\varepsilon_{cu3}$，具体取决于设计时选用的应力-应变模型 [Ref-5]。
   - 若采用**抛物线-矩形**应力-应变关系，极限压应变限值为 $\varepsilon_{cu2}$ [Ref-3], [Ref-9]。
   - 若采用**双线性**应力-应变关系，极限压应变限值为 $\varepsilon_{cu3}$ [Ref-3], [Ref-9]。

2. **近似轴心受压区域**
   在截面中承受近似同心荷载的部分（偏心距 $e/h < 0.1$，例如箱梁的受压翼缘），该部分的**平均压应变**应限制为达到最大强度时的应变 $\varepsilon_{c2}$（若使用双线性模型则为 $\varepsilon_{c3}$） [Ref-5]。

3. **约束混凝土（Confined Concrete）**
   当混凝土受到有效的侧向约束（如通过封闭箍筋或拉筋产生侧向压应力）时，其应力-应变关系会发生改变，不仅强度提高，其**极限压应变也会相应提高** [Ref-6], [Ref-10]。此时需根据侧向有效压应力 $\sigma_2$ 按约束混凝土的专门公式计算提高后的极限应变 [Ref-6], [Ref-10]。

### ⚠️ 现有证据不足说明
**根据当前检索结果无法确定具体的应变数值。** 
当前检索到的证据中仅提供了极限应变的符号定义（$\varepsilon_{cu2}$、$\varepsilon_{cu3}$、$\varepsilon_{c2}$ 等）并指出其来源于 **Table 3.1**，但**未包含 Table 3.1 的具体数值表格**。因此，无法直接为您提供不同混凝土强度等级（如 C50/60 以下或高强混凝土）对应的具体应变限值（例如常规非高强混凝土的 $\varepsilon_{cu2}$ 通常为 0.0035）。**请务必查阅 EN 1992-1-1 规范原文的 Table 3.1 以获取准确数值。**

### 依据位置
- 一般受弯/压弯应变限值及轴心受压限值：EN 1992-1-1 第 6.1 节 (3)P 和 (5) [Ref-5]
- 应力-应变模型定义（$\varepsilon_{cu2}$, $\varepsilon_{cu3}$）：EN 1992-1-1 第 3.1.7 节 [Ref-3], [Ref-9]
- 约束混凝土应变提高：EN 1992-1-1 第 3.1.9 节 [Ref-6], [Ref-10]

### 来源

- [1] DG_EN1992-1-1__-1-2，页 70，条款 : Ductility is defined using the strain at maximum load $( \varepsilon _ { \mathrm { u k } } )$ and the ratio between the maximum and the yield strengths $( f _ { \mathrm { t } } / f _ { \mathrm { y } } ) _ { \mathrm { l } }$ k. Ductility is
- [2] DG_EN1992-1-1__-1-2，页 69，条款 Table 4.10: Table 4.10. Ductility classes for bars, decoiled rods and wire fabrics <table><tr><td></td><td>Ductility class A</td><td>Ductility class B</td><td>Ductility class C</td></tr><tr><td> $k = ( f _ { \mathrm { t } } / f _ { \mathrm { y } } ) _
- [3] EN1992-1-1_2004，页 34，条款 3.1.7: (1) For the design of cross-sections, the following stress-strain relationship may be used, see Figure 3.3 (compressive strain shown positive): (3.18) where: n is the exponent according to Table 3.1 $\varepsilon _ { \mathsf { C } 2 }$ is
- [4] EN1992-1-1_2004，页 34，条款 : $$ \begin{array} { r l } & { \sigma _ { \mathrm { c } } = f _ { \mathrm { c d } } \left[ 1 - \left( 1 - \frac { \mathcal { E } _ { \mathrm { c } } } { \mathcal { E } _ { \mathrm { c } 2 } } \right) ^ { \mathrm { n } } \right] \quad \mathrm
- [5] EN1992-1-1 2004，页 83，条款 6.1, (1)P: (1)P This section applies to undisturbed regions of beams, slabs and similar types of members for which sections remain approximately plane before and after loading. The discontinuity regions of beams and other members in which plane
- [6] EN1992-1-1_2004，页 36，条款 3.1.9: (1) Confinement of concrete results in a modification of the effective stress-strain relationship: higher strength and higher critical strains are achieved. The other basic material characteristics may be considered as unaffected for
- [7] EN1992-1-1_2004，页 27，条款 3.1.1, (1)P: (1)P The following clauses give principles and rules for normal and high strength concrete. (2) Rules for lightweight aggregate concrete are given in Section 11. (1)P The compressive strength of concrete is denoted by concrete strength
- [8] EN1992-1-1_2004，页 69，条款 5.8.6, (1)P: (1)P The general method is based on non-linear analysis, including geometric non-linearity i.e. second order effects. The general rules for non-linear analysis given in 5.7 apply. (2)P Stress-strain curves for concrete and steel suitable

## 14. 极限受力状态下混凝土受压区高度限值为多少？

- Excel 行号: 15
- 层级: Level 2 / 构件极限状态计算层

### 答案

### 直接结论
在承载能力极限状态（ULS）下，欧洲规范 EN 1992-1-1 并未直接规定一个固定的“混凝土受压区高度”绝对限值，而是通过限制**中性轴深度（neutral axis depth, $x_u$ 或 $x$）与截面有效高度（$d$）的比值（$x_u/d$）** 来进行控制 [Ref-8]。该限值主要取决于**弯矩重分布（redistribution）的程度**、**混凝土强度**以及**钢筋的延性等级** [Ref-8]。

---

### 规范限值公式与条件
根据 EN 1992-1-1 第 5.5 节，对于主要受弯且相邻跨度比在 0.5 到 2 之间的连续梁或板，在进行弯矩重分布且无需显式验算转动能力时，中性轴深度比值 $x_u/d$ 必须满足以下条件 [Ref-8, Ref-10]：

**1. 基于混凝土强度的限值公式：**
* 当 $f_{ck} \le 50 \text{ MPa}$ 时：$\delta \ge k_1 + k_2 \frac{x_u}{d}$  [Ref-8]
* 当 $f_{ck} > 50 \text{ MPa}$ 时：$\delta \ge k_3 + k_4 \frac{x_u}{d}$  [Ref-8]

**2. 基于钢筋延性等级的绝对下限：**
* 使用 B 级和 C 级钢筋时：$\delta \ge k_5$  [Ref-8]
* 使用 A 级钢筋时：$\delta \ge k_6$  [Ref-8]

**参数说明与推荐值**（具体需查阅所在国的国家附录） [Ref-8]：
* $\delta$：重分布后的弯矩与弹性弯矩的比值。
* $x_u$：重分布后极限状态下的中性轴深度。
* $d$：截面有效高度。
* $k_1 = 0.44$
* $k_2 = 1.25(0.6 + 0.0014 / \varepsilon_{cu2})$ （$\varepsilon_{cu2}$ 为混凝土极限压应变）
* $k_3 = 0.54$
* $k_4 = 1.25(0.6 + 0.0014 / \varepsilon_{cu2})$
* $k_5 = 0.7$
* $k_6 = 0.8$

---

### 指南参考限值表
根据限值表
根据设计指南（DG_EN1992-1-1）提供的参考表（Table 3.1），在不同弯矩重分布比例（$\delta$）和混凝土强度下，中性轴深度比值 $x/d$ 的限值参考如下 [Ref-2]：

| 弯矩比值 $\delta$ | $f_{ck} \le 50 \text{ MPa}$ | $f_{ck} = 55 \text{ MPa}$ | $f_{ck} = 60 \text{ MPa}$ | $f_{ck} = 70 \text{ MPa}$ | $f_{ck} = 80, 90 \text{ MPa}$ |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **0.90** (重分布10%) | 0.460 | 0.342 | 0.332 | 0.322 | 0.316 |
| **0.85** (重分布15%) | 0.410 | 0.295 | 0.286 | 0.277 | 0.272 |
| **0.80** (重分布20%) | 0.360 | 0.247 | 0.240 | 0.232 | 0.228 |
| **0.70** (重分布30%) | 0.260 | 0.152 | 0.148 | 0.143 | 0.140 |

---

### 受压区高度与中性轴深度的换算
规范直接限制的是中性轴深度 $x_u$。若需计算等效矩形**混凝土受压区高度**，需将其乘以系数 $\lambda$（即 等效受压区高度 = $\lambda x_u$） [Ref-4, Ref-17]。
* 对于 $f_{ck} \le 50 \text{ MPa}$ 的混凝土，$\lambda = 0.8$ [Ref-17]。
* 对于高强混凝土，$\lambda$ 值随强度增加而递减（例如 C55 为 0.788，C90 为 0.700） [Ref-17]。

---

### 注意事项
1. **国家附录差异**：上述 $k_1$ 至 $k_6$ 的数值为欧洲规范推荐值，实际工程中**必须采用项目所在国国家附录（National Annex）中规定的具体数值** [Ref-8]。
2. **适用范围限制**：上述免算转动能力的限值规则仅适用于主要受弯、且相邻跨度比在 0.5 到 2 之间的连续梁或板 [Ref-8]。对于柱构件，必须使用框架作用产生的弹性弯矩，**不得进行任何弯矩重分布** [Ref-8]。
3. **未重分布情况**：如果不进行弯矩重分布（即纯弹性分析，$\delta = 1.0$），规范第 5.5 节未对 $x_u/d$ 设定明确的上限公式，但截面设计仍需满足基本的平衡条件和延性要求。

---

### 依据位置
* **规范公式与重分布条件**：EN 1992-1-1 第 5.5 节 (4) [Ref-8, Ref-10]
* **指南中性轴深度限值表**：DG_EN1992-1-1 Table 3.1 [Ref-2]
* **混凝土应力块参数 $\lambda$**：DG_EN1992-1-1 Table 5.2 [Ref-17]
* **柱构件不可重分布规定**：EN 1992-1-1 第 5.5 节 (6) [Ref-8]

### 来源

- [1] DG_EN1992-1-1__-1-2，页 76，条款 : The conditions in a singly reinforced rectangular section at the ultimate limit state are assumed to be as shown in Fig. 5.5. From Fig. 5.5, it will be seen that the following equations can be derived from consideration of equilibrium of
- [2] DG_EN1992-1-1__-1-2，页 46，条款 Table 3.1: Table 3.1. Limiting neutral axis depths and redistribution of moment <table><tr><td colspan="6"> $x / d$ </td></tr><tr><td>8</td><td> $f _ { \mathtt { c k } } \leq 5 0 \mathsf { M P a }$ </td><td> $f _ { \mathrm { c k } } = 5 5 \mathsf { M
- [3] DG_EN1992-1-1__-1-2，页 74，条款 Table 5.3: Table 5.3. Comparison of stress block parameters <table><tr><td rowspan="2">Grade</td><td colspan="2">Parabolic-rectangular</td><td colspan="2">Bi-linear rectangular</td><td colspan="2">Rectangular</td></tr><tr><td>Average stress
- [4] DG_EN1992-1-1__-1-2，页 71，条款 : The information required to obtain the design stress-strain curves for concrete, ordinary reinforcement and prestressing steel are to be found in clauses 3.1.7, 3.2.3 and 3.3.3, respectively, of EN 1992-1-1. For reinforcement and
- [5] DG_EN1992-1-1__-1-2，页 76，条款 : The conditions in a singly reinforced rectangular section at the ultimate limit state are assumed to be as shown in Fig. 5.5. From Fig. 5.5, it will be seen that the following equations can be derived from consideration of equilibrium of
- [6] EN1992-1-1 2004，页 195，条款 : $f _ { \mathrm { c v d } }$ is the concrete design strength in shear and compression $f _ { \scriptscriptstyle \mathrm { C d } }$ is the concrete design strength in compression $f _ { \mathrm { c t d } }$ is concrete design strength in
- [7] EN1992-1-1_2004，页 195，条款 12.6.3: (1) In plain concrete members account may be taken of the concrete tensile strength in the ultimate limit state for shear, provided that either by calculations or by experience brittle failure can be excluded and adequate resistance can be
- [8] EN1992-1-1 2004，页 60，条款 5.5, (1)P: (1)P The influence of any redistribution of the moments on all aspects of the design shall be considered. (2) Linear analysis with limited redistribution may be applied to the analysis of structural members for the verification of ULS. (3)

## 15. 弯矩重分布限值为多少？

- Excel 行号: 16
- 层级: Level 2 / 构件极限状态计算层

### 答案

**直接结论**
在 Eurocode 2 (EN 1992-1-1) 中，弯矩重分布（Moment Redistribution）的限值并非单一固定数值，而是通过**重分布后弯矩与弹性弯矩的比值（$\delta$）**以及**相对受压区高度（$x_u/d$）**来综合控制。具体限值取决于所采用的分析方法（带有限重分布的线性弹性分析或塑性分析）、钢筋延性等级以及混凝土强度等级。

**依据与说明**

### 1. 带有限重分布的线性弹性分析 (Linear elastic analysis with limited redistribution)
对于主要受弯的连续梁或板，且相邻跨度比在 0.5 到 2 之间时，可不进行转动能力的显式验算而直接进行弯矩重分布，但必须满足以下限值 [Ref-5, Ref-7]：

*   **弯矩比值 $\delta$ 限值**（$\delta$ = 重分布后弯矩 / 弹性弯矩）：
    *   使用 **B级和C级钢筋** 时：$\delta \ge k_5$（规范推荐值 $k_5 = 0.7$，即最大允许重分布 30%）[Ref-5, Ref-6, Ref-7]。
    *   使用 **A级钢筋** 时：$\delta \ge k_6$（规范推荐值 $k_6 = 0.8$，即最大允许重分布 20%）[Ref-5, Ref-6, Ref-7]。
    *   *注：$\delta$ 还需满足与受压区高度相关的公式要求，例如对于 $f_{ck} \le 50$ MPa 的混凝土，需满足 $\delta \ge k_1 + k_2 (x_u/d)$ [Ref-10]。*
*   **相对受压区高度 $x_u/d$ 限值**（重分布后的极限状态）：
    *   混凝土强度 $\le$ C50/60 时：$x_u/d \le 0.45$ [Ref-1, Ref-8, Ref-14]。
    *   混凝土强度 $\ge$ C55/67 时：$x_u/d \le 0.35$ [Ref-1, Ref-8, Ref-14]。

### 2. 塑性分析 (Plastic analysis)
若采用塑性分析，根据是否显式验算转动能力，其限值要求更为严格：

*   **无需显式验算转动能力的条件** [Ref-4, Ref-13, Ref-14]：
    *   受拉钢筋面积必须受限，使得任何截面的 $x_u/d$ 满足：
        *   混凝土 $\le$ C50/60：$x_u/d \le 0.25$
        *   混凝土 $\ge$ C55/67：$x_u/d \le 0.15$
    *   必须使用 B级或 C级钢筋（不推荐使用A级钢筋）[Ref-8, Ref-14]。
    *   中间支座弯矩与跨中弯矩的比值必须在 0.5 到 2 之间 [Ref-4, Ref-13, Ref-14]。
*   **考虑转动能力时的绝对限值**（塑性铰区域） [Ref-8, Ref-14]：
    *   混凝土 $\le$ C50/60：$x_u/d$ 不得超过 0.45。
    *   混凝土 $\ge$ C55/67：$x_u/d$ 不得超过 0.35。

### 3. 禁止进行弯矩重分布的情况
*   **柱子设计**：必须使用框架作用产生的弹性弯矩，**不得**进行任何弯矩重分布 [Ref-6, Ref-7]。
*   **转动能力无法可靠定义的区域**：例如预应力框架的角部，不应进行弯矩重分布 [Ref-6, Ref-7, Ref-7]。

**重要提醒（适用条件与国家附录）**
1.  **国家附录 (National Annex)**：上述提到的参数 $k_1$ 至 $k_6$ 的数值为 Eurocode 的**推荐值**。具体工程所在国的国家附录可能会对这些系数进行修改，设计时必须查阅当地的国家附录以获取法定取值 [Ref-6, Ref-7]。
2.  **平衡要求**：无论采用何种重分布方法，重分布后的弯矩分布必须始终与施加的荷载保持静力平衡 [Ref-5, Ref-7]。
3.  **使用阶段验算**：在进行塑性分析或弯矩重分布后，仍需对结构在使用极限状态（SLS）下的行为（如裂缝宽度、挠度）进行评估和验算 [Ref-4, Ref-13]。

**依据位置**
*   [Ref-5], [Ref-7] EN 1992-1-1 第 5.5 节 (Linear elastic analysis with limited redistribution)
*   [Ref-6] EN 1992-1-1 第 5.5 节 Note (推荐值 $k_1 \sim k_6$)
*   [Ref-8], [Ref-14] EN 1992-1-1 第 5.6 节 (Plastic analysis & Rotation capacity)
*   [Ref-10] EN 1992-1-1 第 5.5 节 公式 (5.10a)
*   [Ref-1], [Ref-4], [Ref-13] DG_EN1992-1-1 指南 第 3.7.2 节及 5.2 节 (补充解释与参数推导)
*   [Ref-6], [Ref-7] EN 1992-1-1 第 5.5(5)P 及 5.5(6) (禁止重分布的情形)

### 来源

- [1] DG_EN1992-1-1__-1-2，页 76，条款 : In applying this formula, some degree of interpretation of the code is necessary since the reader is referred to Table 3.1 of EN 1992-1-1 for values of the ultimate strain. Table 3.1 gives several values, and it has been assumed that the
- [2] DG_EN1992-1-1__-1-2，页 46，条款 Table 3.1: Table 3.1. Limiting neutral axis depths and redistribution of moment <table><tr><td colspan="6"> $x / d$ </td></tr><tr><td>8</td><td> $f _ { \mathtt { c k } } \leq 5 0 \mathsf { M P a }$ </td><td> $f _ { \mathrm { c k } } = 5 5 \mathsf { M
- [3] DG_EN1992-1-1__-1-2，页 74，条款 Table 5.3: Table 5.3. Comparison of stress block parameters <table><tr><td rowspan="2">Grade</td><td colspan="2">Parabolic-rectangular</td><td colspan="2">Bi-linear rectangular</td><td colspan="2">Rectangular</td></tr><tr><td>Average stress
- [4] DG_EN1992-1-1__-1-2，页 46，条款 : Apart from moment redistribution, EN 1992-1-1 allows the use of plastic analysis without any direct check on rotation capacity, provided certain conditions are satisfied: (1) The area of reinforcement at any location in any direction
- [5] EN1992-1-1_2004，页 60，条款 5.5, (1)P: (1)P The influence of any redistribution of the moments on all aspects of the design shall be considered. (2) Linear analysis with limited redistribution may be applied to the analysis of structural members for the verification of ULS. (3)
- [6] EN1992-1-1_2004，页 61，条款 : Note: The values of $k _ { 1 , } k _ { 2 , } k _ { 3 , } k _ { 4 , } k _ { 5 }$ and $k _ { 6 }$ for use in a Country may be found in its National Annex. The recommended value for $k _ { 1 } \mathrm { i } \mathsf { s } 0 , 4 4$ , for
- [7] EN1992-1-1 2004，页 60，条款 5.5, (1)P: (1)P The influence of any redistribution of the moments on all aspects of the design shall be considered. (2) Linear analysis with limited redistribution may be applied to the analysis of structural members for the verification of ULS. (3)
- [8] EN1992-1-1_2004，页 62，条款 5.6.3: (1) The simplified procedure for continuous beams and continuous one way spanning slabs is based on the rotation capacity of beam/slab zones over a length of approximately 1,2 times the depth of section. It is assumed that these zones

## 16. fcd 如何计算

- Excel 行号: 17
- 层级: Level 1 / 基础概念与符号体系层

### 答案

### 直接结论
混凝土抗压强度设计值 $f_{cd}$ 的基本计算公式为：
$$f_{cd} = \alpha_{cc} \frac{f_{ck}}{\gamma_c}$$

### 依据与说明
- **$f_{ck}$**：混凝土的特征圆柱体抗压强度（characteristic cylinder strength），根据混凝土强度等级确定 [Ref-1]。
- **$\gamma_c$**：混凝土的材料分项系数（partial safety factor for concrete），具体取值需参考规范 2.4.2.4 节或项目所在国的国家附录 [Ref-1]。在常规持久和短暂设计状况下，通常取 1.5 [Ref-23]。
- **$\alpha_{cc}$**：考虑长期效应对抗压强度的不利影响以及荷载施加方式不利影响的转换系数 [Ref-1]。
  - **普通混凝土**：规范推荐值为 1（或 1.0），但各国国家附录（National Annex）规定的取值范围在 0.8 到 1.0 之间（例如许多国家实际采用 0.85）[Ref-1]。
  - **轻骨料混凝土（LWAC）**：对应的系数记为 $\alpha_{lcc}$，规范推荐值为 0.85 [Ref-9]。
- **龄期修正（前提条件）**：如果混凝土强度是在龄期 $t > 28$ 天时确定的（例如某些预应力场景），上述 $\alpha_{cc}$ 值还应乘以折减系数 $k_t$（规范推荐值为 0.85，具体见国家附录）[Ref-1]。

### 计算步骤
1. **确定 $f_{ck}$**：根据设计选用的混凝土强度等级（如 C30/37），查表获取对应的特征抗压强度 $f_{ck}$（如 30 MPa）[Ref-2]。
2. **确定 $\gamma_c$**：根据设计状况（持久/短暂、偶然或疲劳）查阅规范 2.4.2.4 节或国家附录，确定材料分项系数（常规情况取 1.5）[Ref-1]。
3. **确定 $\alpha_{cc}$**：**必须查阅项目所在国的国家附录（National Annex）** 以获取确切值。若无特殊规定且采用规范推荐值，普通混凝土取 1.0，轻骨料混凝土取 0.85 [Ref-1], [Ref-9]。
4. **执行计算**：将上述参数代入公式 $f_{cd} = \alpha_{cc} f_{ck} / \gamma_c$ 得出设计强度。若涉及 $t > 28$ 天的后期强度评估，需额外乘以 $k_t$ [Ref-1]。

### 指南参考案例
- **案例背景**：矩形柱截面设计（Example 5.3）[Ref-23]。
- **核心步骤**：已知混凝土特征强度 $f_{ck} = 30$ MPa，案例中取 $\alpha_{cc} = 0.85$，材料分项系数 $\gamma_m$（即 $\gamma_c$）= 1.5 [Ref-23]。
- **计算过程**：$f_{cd} = 0.85 \times 30 / 1.5 = 17 \text{ MPa}$ [Ref-23]。
- **对应说明**：该案例展示了 $\alpha_{cc}$ 取 0.85 时的计算路径。工程师在实际应用中，必须核实本国国家附录对 $\alpha_{cc}$ 的具体取值要求，不可盲目照搬指南案例中的数值。

### 依据位置
- 普通混凝土 $f_{cd}$ 公式及参数定义：EN 1992-1-1:2004, 3.1.6 (1)P [Ref-1]
- 轻骨料混凝土 $f_{cd}$ 规定：EN 1992-1-1:2004, 11.3.5 (1)P [Ref-9]
- 龄期 $t > 28$ 天的折减规定：EN 1992-1-1:2004, 3.1.2 (4) [Ref-1]
- 混凝土强度等级与 $f_{ck}$ 对应表：EN 1992-1-1:2004, Table 3.1 [Ref-2]
- 指南算例参考：DG EN 1992-1-1, Example 5.3 [Ref-23]-23]

### 来源

- [1] EN1992-1-1_2004，页 27，条款 3.1.1, (1)P: (1)P The following clauses give principles and rules for normal and high strength concrete. (2) Rules for lightweight aggregate concrete are given in Section 11. (1)P The compressive strength of concrete is denoted by concrete strength
- [2] EN1992-1-1 2004，页 28，条款 Table 3.1: Table 3.1 Strength and deformation characteristics for concrete <table><tr><td rowspan=1 colspan=15> Strength classes for concrete</td><td rowspan=1 colspan=1>Analytical relation/ Explanation</td></tr><tr><td rowspan=1 colspan=1>fck
- [3] EN1992-1-1 2004，页 32，条款 Table 3.2: Table 3.2 Nominal unrestrained drying shrinkage values ${ \pmb \varepsilon } _ { { \mathsf { c d } } , { \mathsf { 0 } } }$ (in ${ { \boldsymbol \circ } } _ { I _ { 0 0 } } )$ for concrete with cement CEM Class N <table><tr><td rowspan=2
- [4] EN1992-1-1_2004，页 30，条款 Table 3.3: Table 3.3 Values for $\pmb { k _ { \mathrm { h } } }$ in Expression (3.9) <table><tr><td> $h _ { 0 }$ </td><td> $\underline { { k _ { \mathrm { h } } } }$
- [5] EN1992-1-1_2004，页 28，条款 : $$ E _ { \mathrm { c m } } ( t ) = \left( f _ { \mathrm { c m } } ( t ) / f _ { \mathrm { c m } } \right) ^ { 0 , 3 } E _ { \mathrm { c m } }\tag{3.5} $$
- [6] EN1992-1-1_2004，页 33，条款 : $$ \frac { \sigma _ { \mathrm { c } } } { f _ { \mathrm { c m } } } = \frac { k \eta - \eta ^ { 2 } } { 1 + \left( k - 2 \right) \eta }\tag{3.14} $$
- [7] EN1992-1-1_2004，页 27，条款 : $$ \begin{array} { r l } { f _ { \mathrm { c k } } ( t ) = f _ { \mathrm { c m } } ( t ) \cdot 8 \ ( \mathsf { M P a } ) \mathsf { f o r } \quad } & { 3 < t < 2 8 \ \mathrm { d a y s } . } \\ { f _ { \mathrm { c k } } ( t ) = f _ { \mathrm
- [8] EN1992-1-1_2004，页 36，条款 : $$ \boldsymbol { f _ { \mathrm { c t m , \uparrow } } } = \mathsf { m a x } \left\{ ( 1 , 6 \cdot h / 1 0 0 0 ) \boldsymbol { f _ { \mathrm { c t m } } } ; \boldsymbol { f _ { \mathrm { c t m } } } \right\}\tag{3.23} $$

## 17. 截面计算中材料分项安全系数为多少？

- Excel 行号: 18
- 层级: Level 1 / 基础概念与符号体系层

### 答案

### 直接结论
在混凝土结构截面计算中，材料分项安全系数的取值主要取决于验算的极限状态（承载能力极限状态或正常使用极限状态）及荷载组合类型。对于承载能力极限状态（ULS）的基本组合，混凝土分项安全系数 $\gamma_C$ 推荐值为 **1.5**，钢筋及预应力筋分项安全系数 $\gamma_S$ 推荐值为 **1.15**。对于正常使用极限状态（SLS），材料分项安全系数通常取 **1.0**。

---

### 依据与详细说明

#### 1. 承载能力极限状态 (ULS)
根据规范，不同组合下的材料分项安全系数推荐值如下 [Ref-1]：
*   **基本组合 (Fundamental)**：混凝土 $\gamma_C = 1.5$；钢筋和预应力筋 $\gamma_S = 1.15$ [Ref-1]。
*   **偶然组合（除火灾外） (Accidental except fire situations)**：混凝土 $\gamma_C = 1.2$；钢筋和预应力筋 $\gamma_S = 1.0$ [Ref-1]。
*   **偶然组合 - 火灾情况 (Accidental - fire situations)**：混凝土 $\gamma_C = 1.0$；钢筋和预应力筋 $\gamma_S = 1.0$ [Ref-1]。

#### 2. 正常使用极限状态 (SLS)
*   在正常使用极限状态计算中，材料属性的分项安全系数通常取 $\gamma_M = 1.0$ [Ref-7] [Ref-10] [Ref-14]。

#### 3. 基于质量控制和偏差减小的折减（附录A）
在满足特定质量控制和尺寸偏差要求的前提下，规范允许对分项安全系数进行折减（以下为规范给出的推荐值）：
*   **折减1**：若质量保证系统确保截面尺寸不利偏差在减小范围内，钢筋 $\gamma_{s,red1}$ 推荐值为 1.1 [Ref-3]；若同时混凝土强度变异系数不超过 10%，混凝土 $\gamma_{c,red1}$ 推荐值为 1.4 [Ref-3]。
*   **折减2**：钢筋 $\gamma_{s,red2}$ 推荐值为 1.05，混凝土 $\gamma_{c,red2}$ 推荐值为 1.45 [Ref-2]。
*   **折减3**：在特定条件且混凝土强度变异系数不超过 10% 时，混凝土 $\gamma_{c,red3}$ 推荐值为 1.35 [Ref-2]。

---

### 适用条件与限制提醒条件与限制提醒（重要）
1. **国家附录 (National Annex) 优先**：上述附录A中的折减系数以及部分基本参数属于国家决定参数 (NDP)。实际工程中**必须**查阅项目所在国的国家附录，以确认是否采用推荐值或使用了其他规定值 [Ref-2] [Ref-3] [Ref-11]。
2. **疲劳验算不适用**：上述 ULS 的基本材料分项安全系数**不适用**于疲劳验算，疲劳验算需采用专门的分项系数 [Ref-10]。
3. **钢筋强度级别**：$\gamma_S = 1.15$ 的取值主要针对特征强度为 500 MPa 的钢筋 [Ref-10]。
4. **材料设计强度的转换系数**：在计算截面材料设计强度（如混凝土抗压/抗拉设计强度）时，除了除以分项安全系数 $\gamma_C$ 外，还需乘以转换系数（如 $\alpha_{cc}$ 和 $\alpha_{ct}$，推荐值为 0.85），以考虑长期荷载效应、尺寸效应及局部缺陷等 [Ref-4] [Ref-8] [Ref-18]。该转换系数的具体取值同样需查阅国家附录 [Ref-4] [Ref-18]。

---

### 依据位置
* [Ref-1] DG_EN1992-1-1__-1-2, Introduction > 2.6.2. Design values, Table 2.6, p.24-25
* [Ref-2] EN1992-1-1 2004, p.200
* [Ref-3] EN1992-1-1 2004, A.2.1, p.199
* [Ref-4] EN1992-1-1_2004, 11.3.5, p.188
* [Ref-7] DG_EN1992-1-1__-1-2, 8.1.2. Material properties, p.140
* [Ref-8] DG_EN1990, 6.3.3, p.77-78
* [Ref-10] DG_EN1992-1-1__-1-2, Introduction > 2.6. Material properties, p.24-25
* [Ref-11] DG_EN1992-1-1__-1-2, Introduction, p.13-61
* [Ref-14] DG_EN1992-1-1__-1-2, 8.1. General, p.139-140
* [Ref-18] EN1992-1-1_2004, 11.3.5, p.188

### 来源

- [1] DG_EN1992-1-1__-1-2，页 24，条款 Table 2.6: Table 2.6. Partial safety factors for material properties\* <table><tr><td>Combination</td><td>Concrete, $\gamma _ { \mathtt { C } }$ </td><td>Reinforcement and prestressing tendons, $\gamma _ { \mathsf { S } }$
- [2] EN1992-1-1 2004，页 200，条款 : the partial safety factors may be reduced to γs,red2 and γc,red2. Note: The values of $\gamma _ { \mathsf { s } , \mathsf { r e d } 2 }$ and $\gamma _ { \mathtt { C } , \mathtt { r e d } 2 }$ for use in a Country may be found in its
- [3] EN1992-1-1 2004，页 199，条款 : (1) If execution is subjected to a quality control system, which ensures that unfavourable deviations of cross-section dimensions are within the reduced deviations given in Table A.1, the partial safety factor for reinforcement may be
- [4] EN1992-1-1 2004，页 188，条款 11.3.5, (1)P: (1)P The value of the design compressive strength is defined as where $\gamma _ { \mathtt { C } }$ is the partial safety factor for concrete, see 2.4.1.4, and $\alpha _ { \mathrm { l c c } }$ is a coefficient according to 3.1.6 (1)P. Note:
- [5] EN1992-1-1_2004，页 16，条款 1.6: P Partial factor for actions associated with prestressing, $P$ Q Partial factor for variable actions, Q S Partial factor for reinforcing or prestressing steel S,fat Partial factor for reinforcing or prestressing steel under fatigue loading
- [6] EN1992-1-1_2004，页 2，条款 : 1. General 1.1 Scope 1.1.1 Scope of Eurocode 2 1.1.2 Scope of Part 1-1 of Eurocode 2 1.2 Normative references 1.2.1 General reference standards 1.2.2 Other reference standards 1.3 Assumptions 1.4 Distinction between principles and
- [7] DG_EN1992-1-1__-1-2，页 140，条款 : Clause 6.5.4 of EN 1990 states that the partial safety factor applied to material properties should generally be 1.0. The properties of the materials which are normally significant in serviceability calculations are the modulus of
- [8] DG_EN1990，页 77，条款 6.3.3: The design value of a resistance may be determined by various means, including: empirical relationships involving measured physical properties or chemical composition (e.g. the composition of a high-strength concrete with silica fume) from

## 18. 混凝土抗压强度标准值、设计值与平均强度之间是什么关系？

- Excel 行号: 19
- 层级: Level 1 / 基础概念与符号体系层

### 答案

### 核心结论
在欧洲规范（Eurocode）中，混凝土抗压强度的平均强度（$f_{cm}$）、标准值（$f_{ck}$）与设计值（$f_{cd}$）之间存在明确的数学换算关系：
1. **平均强度与标准值**：$f_{cm} = f_{ck} + 8 \text{ MPa}$ （针对28天龄期圆柱体强度）。
2. **标准值与设计值**：$f_{cd} = \alpha_{cc} \frac{f_{ck}}{\gamma_c}$。

---

### 详细关系说明

#### 1. 平均强度 ($f_{cm}$) 与 标准值 ($f_{ck}$) 的关系
* **标准值的定义**：混凝土抗压强度标准值 $f_{ck}$ 是指28天圆柱体抗压强度的5%分位值，即在所有测试结果中，仅有不超过5%的概率会低于该强度值 [Ref-5, Ref-7]。
* **数值换算**：在28天龄期时，混凝土圆柱体平均抗压强度 $f_{cm}$ 与标准值 $f_{ck}$ 的差值恒为 8 MPa，即 $f_{cm} = f_{ck} + 8 \text{ MPa}$ [Ref-8, Ref-16, Ref-18]。
* **早龄期关系**：对于 $3 < t < 28$ 天的早龄期混凝土，其标准值与平均强度的关系同样为 $f_{ck}(t) = f_{cm}(t) - 8 \text{ MPa}$ [Ref-8, Ref-16]。

#### 2. 标准值 ($f_{ck}$) 与 设计值 ($f_{cd}$) 的关系
* **设计值的计算**：抗压强度设计值 $f_{cd}$ 是通过将标准值 $f_{ck}$ 除以混凝土材料分项安全系数 $\gamma_c$，并乘以转换系数 $\alpha_{cc}$ 来确定的 [Ref-6, Ref-11]。
* **计算公式**：$f_{cd} = \alpha_{cc} \frac{f_{ck}}{\gamma_c}$ [Ref-6, Ref-11]。

---

### 关键参数与适用条件提醒
* **系数 $\alpha_{cc}$**：该系数用于考虑长期荷载效应对抗压强度的影响以及加载方式带来的不利影响 [Ref-11, Ref-13]。规范推荐值为 **1.0**，但具体取值（通常在 0.8 到 1.0 之间）**必须查阅项目所在国的国家附录（National Annex）** [Ref-11]。例如，英国国家附录（UK NA）推荐取值为 0.85 [Ref-13]。
* **材料分项系数 $\gamma_c$**：用于覆盖材料性能可能出现的不利偏差，其具体数值需根据设计状况（如持久、短暂或偶然状况）及国家附录确定 [Ref-2, Ref-11]。
* **试件形状差异**：上述 $f_{cm}$ 与 $f_{ck}$ 的直接加减关系基于**圆柱体试件（cylinder）**。若使用立方体试件（cube），其标准值记为 $f_{ck,cube}$，圆柱体与立方体标准值之间存在特定的换算关系，需查阅规范中的强度等级对照表（如 EN 1992-1-1 的 Table 3.1） [Ref-5, Ref-18]。

---

### 依据位置
* **符号定义**：EN 1992-1-1:2004, 1.6 [Ref-1]
* **标准值定义及与平均强度关系**：EN 1992-1-1:2004, 3.1.2 [Ref-5, Ref-8, Ref-16]
* **设计值计算公式**：EN 1992-1-1:2004, 3.1.6(1)P [Ref-11]；DG EN 1990, 6.3.3 [Ref-6]
* **强度等级与参数对照表**：DG EN 19921992-1-1, Table 4.1 [Ref-18]
* **$\alpha_{cc}$ 系数说明及国家附录差异**：DG EN 1992-1-1, 4.1 [Ref-13]

### 来源

- [1] EN1992-1-1_2004，页 16，条款 1.6: $d _ { \mathfrak { g } }$ Largest nominal maximum aggregate size $\pmb { \theta }$ Eccentricity $\pmb { f } _ { \mathtt { C } }$ Compressive strength of concrete $\pmb { f } _ { \mathrm { c d } }$ Design value of concrete compressive
- [2] DG_EN1990，页 77，条款 6.3.3: The design value of a resistance may be determined by various means, including: empirical relationships involving measured physical properties or chemical composition (e.g. the composition of a high-strength concrete with silica fume) from
- [3] DG EN1990，页 77，条款 6.3.3: The design value of a resistance may be determined by various means, including: empirical relationships involving measured physical properties or chemical composition (e.g. the composition of a high-strength concrete with silica fume) from
- [4] EN1992-1-1_2004，页 27，条款 3.1.2, (1)P: temperature and curing conditions. For a mean temperature of $\scriptstyle 2 0 ^ { \circ } \complement$ and curing in accordance with EN 12390 the compressive strength of concrete at various ages $\pmb { f } _ { \mathsf { c m } } ( t )$
- [5] EN1992-1-1_2004，页 27，条款 3.1.2, (1)P: (1)P The compressive strength of concrete is denoted by concrete strength classes which relate to the characteristic (5%) cylinder strength $\pmb { f } _ { \mathtt { C k } } ,$ , or the cube strength $f _ { \mathtt { C K , C u b e } }$ ,
- [6] DG EN1990，页 77，条款 : $$ f _ { \mathrm { c d } } = \alpha _ { \mathrm { c c } } \frac { f _ { \mathrm { c k } } } { \gamma _ { \mathrm { c } } } $$
- [7] DG_EN1992-1-1__-1-2，页 63，条款 : In EN 1992-1-1 the compressive strength of concrete is denoted by concrete strength classes, which relate to the characteristic cylinder strength $f _ { \mathrm { c k } }$ or the cube strength $\bar { f } _ { \mathrm { c k , c u b e } } .$
- [8] EN1992-1-1 2004，页 27，条款 3.1.2, (1)P: (1)P The compressive strength of concrete is denoted by concrete strength classes which relate to the characteristic $( 5 \% )$ cylinder strength $\pmb { f } _ { \mathtt { C } \mathtt { K } }$ , or the cube strength $\pmb { f } _ { \mathtt

## 19. 钢筋的锚固长度与搭接长度受哪些因素影响？

- Excel 行号: 20
- 层级: Level 3 / 构造规定与抗震补充层

### 答案

根据欧洲规范 EN 1992-1-1 及其相关设计指南，钢筋的锚固长度与搭接长度受钢筋自身属性、混凝土性能、构造细节及受力状态等多方面因素的综合影响。具体影响因素可划分为以下三个层次：

### 一、 影响基本锚固长度（$l_{b,rqd}$）的核心因素
基本锚固长度是计算设计锚固长度和搭接长度的基础，主要受以下因素影响：
1. **钢筋特性**：包括钢筋直径（$\phi$）、钢筋在设计截面处的设计应力（$\sigma_{sd}$）以及钢筋的表面特征（如光圆或带肋）[Ref-2, Ref-4, Ref-11, Ref-14]。对于大直径钢筋，其极限粘结应力会有所降低 [Ref-2, Ref-4]。
2. **混凝土性能**：极限粘结应力主要取决于混凝土的抗拉强度设计值（$f_{ctd}$ 或 $f_{ctk}$）[Ref-2, Ref-4, Ref-11]。
3. **粘结条件（Bond condition）**：与钢筋在混凝土中的位置及浇筑方向有关。规范将其分为“良好（good）”和“较差（poor）”两种粘结条件，较差的粘结条件会显著降低粘结应力（折减系数 $\eta_1 = 0.7$）[Ref-2, Ref-4, Ref-11]。

### 二、 影响设计锚固长度（$l_{bd}$）的构造与修正因素
设计锚固长度是在基本锚固长度的基础上，通过乘以一系列修正系数（$\alpha_1 \sim \alpha_5$）来确定的，主要受以下构造和受力因素影响：
1. **钢筋形状（$\alpha_1$）**：直筋、标准弯钩、弯折或环形等不同锚固形状的影响 [Ref-4, Ref-9, Ref-11]。
2. **混凝土保护层厚度（$\alpha_2$）**：最小混凝土保护层厚度或钢筋净距对劈裂裂缝的约束影响 [Ref-4, Ref-9, Ref-11]。
3. **横向钢筋约束（$\alpha_3$）**：非焊接横向钢筋（如箍筋）提供的约束作用 [Ref-4, Ref-9, Ref-11]。
4. **焊接横向钢筋（$\alpha_4$）**：沿设计锚固长度内存在的焊接横向钢筋（直径 $>0.6\phi$）的影响 [Ref-4]。
5. **横向压力（$\alpha_5$）**：垂直于潜在劈裂面的横向压力影响 [Ref-4, Ref-9, Ref-11]。
*注：设计锚固长度还必须满足规范规定的最小锚固长度（$l_{b,min}$）限值要求 [Ref-4]。*

### 三、 影响搭接长度（$l_0$）的特有因素
搭接长度基于基本锚固长度计算，因此受上述所有基本因素的影响 [Ref-3, Ref-7]。此外，还受以下搭接特有因素影响：
1. **同一截面搭接钢筋比例（$\alpha_6$）**：同一截面（包含该截面两侧 $0.65l_0$ 范围内）搭接钢筋面积占总钢筋面积的比例（$\rho_1$）。当搭接比例大于 50% 时，搭接长度需乘以 1.0 至 1.5 的放大系数 [Ref-3, Ref-7]。
2. **搭接钢筋的净距**：当搭接钢筋之间的净距大于 4 倍钢筋直径（$4\phi$）时，搭接长度需要增加，增加量等于净距超出 $4\phi$ 的部分 [Ref-9]。

### 四、 国家附录与适用条件提示
- **大直径钢筋折减差异**：欧洲规范 EN 1992-1-1 规定当钢筋直径 $\phi > 32\text{ mm}$ 时需对粘结应力进行折减（系数 $\eta_2$）[Ref-4]。但在**英国国家附录（UK National Annex）** 中，大直径钢筋被定义为 $\phi > 40\text{ mm}$，且其折减计算公式与欧洲规范原版存在差异 [Ref-2, Ref-11]。工程师在实际项目中需确认所适用国家附录的具体规定。
- **高强混凝土限制**：由于高强混凝土的脆性增加，在计算粘结粘结应力时，混凝土抗拉强度特征值（$f_{ctk,0.05}$）的上限被限制为 C60/75 强度等级的值，除非能证明平均粘结强度在此限值之上仍有提高 [Ref-4]。

### 依据位置
- **基本锚固长度与粘结应力**：[Ref-1] (6.6节), [Ref-2] (10.2.4节), [Ref-4] (8.4.2节, 8.4.3节), [Ref-5] (8.4.3节), [Ref-8] (6.6节), [Ref-10] (8.4.3节), [Ref-11] (Detailing章节), [Ref-13] (10.2节), [Ref-14] (公式8.3)
- **设计锚固长度修正系数**：[Ref-4] (8.4.4节及Table 8.2相关说明), [Ref-9] (10.3节), [Ref-11] (Detailing章节)
- **搭接长度及特有修正系数**：[Ref-3] (10.5节), [Ref-7] (10.5.2节), [Ref-9] (图10.6说明)

### 来源

- [1] EN1992-1-1_2004，页 111，条款 6.6, (1)P: (1)P The design bond stress is limited to a value depending on the surface characteristics of the reinforcement, the tensile strength of the concrete and confinement of surrounding concrete. This depends on cover, transverse reinforcement
- [2] DG_EN1992-1-1__-1-2，页 194，条款 : In EN 1992-1-1 the parameter $l _ { \mathrm { b , r e q d } }$ (basic anchorage length) is used in the calculation of design anchorage and lap lengths: where $\phi$ is the diameter of the bar, $\sigma _ { \mathrm { s d } }$ is the stress
- [3] DG_EN1992-1-1__-1-2，页 199，条款 : As the length of reinforcement bars is generally likely to be less than the length of the structure, lapping (or splicing) of bars will be necessary in most structural elements. At laps, forces are transmitted from one bar to another. This
- [4] EN1992-1-1_2004，页 132，条款 8.4.1, (1)P: (1)P Reinforcing bars, wires or welded mesh fabrics shall be so anchored that the bond forces are safely transmitted to the concrete avoiding longitudinal cracking or spalling. Transverse reinforcement shall be provided if necessary. (2)
- [5] EN1992-1-1_2004，页 134，条款 8.4.3, (1)P: (1)P The calculation of the required anchorage length shall take into consideration the type of steel and bond properties of the bars. (2) The basic required anchorage length, $I _ { \mathrm { b , r q d } } ,$ for anchoring the force $A _
- [6] EN1992-1-1_2004，页 132，条款 8.4.1, (1)P: (1)P Reinforcing bars, wires or welded mesh fabrics shall be so anchored that the bond forces are safely transmitted to the concrete avoiding longitudinal cracking or spalling. Transverse reinforcement shall be provided if necessary. (2)
- [7] DG_EN1992-1-1__-1-2，页 199，条款 : Design lap length is calculated by modifying the basic anchorage length (see Section 10.2.4 above) by applying multipliers: where $\alpha _ { 1 } , \alpha _ { 2 } , \alpha _ { 3 }$ and $\alpha _ { 5 }$ are as discussed for anchorage and
- [8] EN1992-1-1 2004，页 111，条款 6.6, (1)P: (1)P The design bond stress is limited to a value depending on the surface characteristics of the reinforcement, the tensile strength of the concrete and confinement of surrounding concrete. This depends on cover, transverse reinforcement

## 20. 什么情况下需要考虑二阶效应？

- Excel 行号: 21
- 层级: Level 4 / 复杂场景与多参数耦合层

### 答案

### 直接结论
在结构设计中，当二阶效应（second order effects）可能显著影响结构的整体稳定性，或影响关键截面达到承载能力极限状态（ULS）时，必须考虑二阶效应 [Ref-4], [Ref-5], [Ref-12]。

### 依据与说明

#### 1. 适用对象与结构类型
二阶效应的相关规定主要针对结构行为受其显著影响的构件和结构，如柱、墙、桩、拱和壳 [Ref-10], [Ref-16]。此外，具有柔性支撑系统的结构极易出现整体二阶效应（global second order effects），需特别关注 [Ref-10], [Ref-16]。

#### 2. 定量判断标准（不满足以下条件时即需考虑）
规范提供了判断是否可以忽略二阶效应的界限，若不满足以下忽略条件，则必须考虑二阶效应：
* **10% 准则**：如果由于二阶变形引起的相关弯矩或侧移剪力的增加，大于或等于相应一阶弯矩或层剪力的 10%，则必须考虑 [Ref-1], [Ref-10], [Ref-16]。此外，若结构内的轴力超过理论屈曲荷载的 10%，也不能忽略整体二阶效应 [Ref-1]。
* **孤立构件（Isolated members）**：如果构件的长细比 $\lambda$ 大于规范规定的限值大于规范规定的限值 $\lambda_{lim}$（该限值与有效徐变比、机械配筋率、相对轴力及端弯矩比有关），则必须考虑二阶效应 [Ref-16]。
* **整体结构（建筑）**：如果不满足 EN 1992-1-1 第 5.8.3.3 条给出的整体二阶效应忽略公式（该公式综合考量了总竖向荷载、层数、建筑总高度、混凝土弹性模量及支撑构件截面惯性矩），则必须考虑整体二阶效应 [Ref-7], [Ref-16]。

#### 3. 伴随间接作用（Indirect actions）时的特殊要求
在承载能力极限状态（ULS）下，某些间接作用通常可忽略，但当二阶效应很重要时，必须将它们与二阶效应结合考虑：
* **温度效应、收缩、差异沉降**：仅当它们对稳定性验证中的二阶效应影响显著时，才需要在 ULS 中予以考虑 [Ref-2], [Ref-3], [Ref-9], [Ref-11], [Ref-15]。
* **徐变（Creep）**：在进行二阶分析时，**必须**考虑徐变的影响，需结合荷载持续时间采用有效徐变比（effective creep ratio）进行计算 [Ref-6]。

#### 4. 分析前提与注意事项
* **变形状态验证**：当考虑二阶效应时，必须在变形后的状态下验证结构的平衡和抗力，且变形计算必须考虑开裂、材料非线性和徐变的相关影响（或在假定线性材料属性时通过折减刚度来考虑） [Ref-10], [Ref-16]。
* **几何缺陷**：必须将几何和轴力位置的不确定性作为基于几何缺陷的附加一阶效应纳入考虑 [Ref-10], [Ref-16]。
* **简化程序限制**：对于规则的钢或混凝土框架，可先进行整体一阶分析，再在构件分析中同时考虑整体和构件二阶效应；但**不应**在不对称或不寻常的情况下使用此简化程序 [Ref-1]。

### 依据位置
* [Ref-1] DG EN1990, Background, p. 69
* [Ref-2], [Ref-9] EN1992-1-1_2004, 2.3.1.2 Thermal effects, p. 21
* [Ref-3], [Ref-15] EN1992-1-1_2004, 2.3.2.2 Shrinkage and creep, p. 22
* [Ref-4], [Ref-5], [Ref-12] EN1992-1-1_2004, 5.1.4 Second order effects, p. 54
* [Ref-6] EN1992-1-1_2004, 5.8.4 Creep, p. 68
* [Ref-7] DG_EN1992-1-1__-1-2, Slender columns and beams, p. 133-137
* [Ref-10], [Ref-16] EN1992-1-1_2004, 5.8.2 General / 5.8 Analysis of second order effects, p. 64-65
* [Ref-11] EN1992-1-1_2004, 2.3.1 Actions and environmental influences, p. 20-22

### 来源

- [1] DG EN1990，页 69，条款 : In the previous version of the Eurocode (ENV 1991-1), an increase of more than $1 0 \%$ in the effects of actions was proposed, but it was recognised that such a value depends on the particular construction and/or its structural material.
- [2] EN1992-1-1_2004，页 21，条款 2.3.1.2: (1) Thermal effects should be taken into account when checking serviceability limit states. (2) Thermal effects should be considered for ultimate limit states only where they are significant (e.g. fatigue conditions, in the verification of
- [3] EN1992-1-1_2004，页 22，条款 2.3.2.2: (1) Shrinkage and creep are time-dependent properties of concrete. Their effects should generally be taken into account for the verification of serviceability limit states. (2) The effects of shrinkage and creep should be considered at
- [4] EN1992-1-1_2004，页 54，条款 5.1.4, (1)P: (1)P Second order effects (see EN 1990 Section 1) shall be taken into account where they are likely to affect the overall stability of a structure significantly and for the attainment of the ultimate limit state at critical sections. (2)
- [5] EN1992-1-1 2004，页 54，条款 5.1.4, (1)P: (1)P Second order effects (see EN 1990 Section 1) shall be taken into account where they are likely to affect the overall stability of a structure significantly and for the attainment of the ultimate limit state at critical sections. (2)
- [6] EN1992-1-1_2004，页 68，条款 5.8.4, (1)P: (1)P The effect of creep shall be taken into account in second order analysis, with due consideration of both the general conditions for creep (see 3.1.4) and the duration of different loads in the load combination considered. (2) The
- [7] DG_EN1992-1-1__-1-2，页 133，条款 : The sections above have been concerned exclusively with cases where the second-order effects act about the same axis as the first-order moments and where only uniaxial moments act. While this will frequently be the case, it will by no
- [8] DG_EN1992-1-1__-1-2，页 38，条款 : As structures subject to lateral loads deflect, the vertical loads acting on the structure produce additional forces and moments. These are normally referred to as second-order effects. Consider a cantilever column shown in Fig. 3.5. The

## 21. 受弯构件正截面承载力计算的一般步骤是什么？

- Excel 行号: 22
- 层级: Level 2 / 构件极限状态计算层

### 答案

### 直接结论
根据当前检索结果，欧洲规范 EN 1992-1-1 正文中未直接以条款形式列出“受弯构件正截面承载力计算的一般步骤”。但相关官方设计指南中提供了一套适用于任意截面（包括受弯和压弯）的**通用迭代计算步骤**，可用于求解正截面抗弯承载力。

### 计算步骤（通用迭代法）
对于无法直接套用简化公式的情况，指南推荐采用以下迭代步骤计算截面的抗弯承载力 [Ref-21]：

1. **假定中和轴深度**：初步猜测一个中和轴深度 $x$ 的值 [Ref-21]。
2. **计算混凝土受压区合力**：使用规范允许的受压应力-应变曲线理想化模型计算受压区的混凝土压力。若采用抛物线-矩形应力图，可能需要数值积分技术；对于简单的手算，采用**矩形应力图**（rectangular idealization）最为简便 [Ref-21]。
3. **计算钢筋内力**：根据假定的中和轴深度和混凝土极限应变，计算每一层钢筋的应变，进而求出对应的钢筋应力和各层钢筋的内力 [Ref-21]。
4. **校核平衡并求解**：
   - 检查截面总压力是否等于总拉力（即满足轴力平衡条件）[Ref-21]。
   - **若平衡**：说明中和轴深度 $x$ 假定正确，直接对内部各力取矩，即可求得截面的抗弯承载力 [Ref-21]。
   - **若不平衡**：调整中和轴深度 $x$ 的值，并返回第2步重新计算，直至满足平衡条件 [Ref-21]。

### T型或L型截面（翼缘梁）的处理原则
- **中和轴在翼缘内**：若极限状态下中和轴位于翼缘厚度范围内，可直接将其等效为矩形截面进行计算 [Ref-21]。
- **中和轴在腹板内**：若中和轴深度大于翼缘厚度，可足够精确地假定翼缘外伸部分全部承受大小为 $f_{cd}$（混凝土设计抗压强度）的均匀压应力 [Ref-21]。此时可将截面分为两部分：翼缘外伸部分承担部分弯矩并配置相应钢筋；剩余弯矩由宽度为腹板宽度的矩形截面承担，最后将两部分所需的最后将两部分所需的受拉钢筋面积相加 [Ref-21]。

### 依据与说明
1. **材料本构模型**：上述步骤中的应力-应变关系需依据 EN 1992-1-1 中关于混凝土（如第 3.1 节）和钢筋的设计本构模型取值 [Ref-17]。
2. **国家附录（National Annex）限制**：计算中涉及的材料分项系数（如 $\gamma_m$）及部分设计参数，必须采用工程项目所在国发布的国家附录中规定的数值，不同国家的取值可能存在差异 [Ref-20]。
3. **现有证据不足提醒**：当前检索证据主要提取自设计指南（DG），关于正截面承载力计算的规范基本假定（如平截面假定等）及规范正文的具体强制条款（如第 6.1 节）未在现有片段中完整体现。实际工程设计时，请务必查阅 EN 1992-1-1 规范正文第 6 章（承载能力极限状态）的相关强制性规定。

### 依据位置
- **通用迭代计算步骤及T/L型截面处理**：DG_EN1992-1-1, Design of sections for bending and axial force > Example 5.2, 页码 79, 80, 89, 90 [Ref-21]。
- **混凝土应力-应变关系**：EN1992-1-1_2004, 3.1.5 Stress-strain relation for non-linear structural analysis, 页码 33, 34 [Ref-17]。
- **国家附录（NDPs）说明**：DG_EN1990, National Annexes, 页码 8 [Ref-20]。

### 来源

- [1] EN1992-1-1 2004，页 88，条款 : $$ V _ { \mathrm { R d , \mathscr { m } a x } } = \alpha _ { \mathrm { c w } } b _ { \mathrm { w } } z \ \nu _ { 1 } \ f _ { \mathrm { c d } } / ( \mathsf { c o t } \theta + \mathsf { t a n } \theta ) $$
- [2] EN1992-1-1 2004，页 88，条款 : $$ V _ { \mathrm { R d , m a x } } = \alpha _ { \mathrm { c w } } b _ { \mathrm { w } } z \nu _ { \mathrm { 1 } } f _ { \mathrm { c d } } ( \mathsf { c o t } \theta \ + \ \mathsf { c o t } \alpha ) / ( 1 \ + \ \mathsf { c o t } ^ { 2 }
- [3] DG_EN1992-1-1__-1-2，页 47，条款 : This takes into account the non-linear deformation properties of reinforced-concrete sections. This method is seldom used in practical design as it is complex, requiring a computer and prior knowledge of reinforcement details throughout
- [4] EN1992-1-1 2004，页 163，条款 9.6.1: (1) This clause refers to reinforced concrete walls with a length to thickness ratio of 4 or more and in which the reinforcement is taken into account in the strength analysis. The amount and proper detailing of reinforcement may be
- [5] EN1992-1-1 2004，页 152，条款 9.1, (1)P: (1)P The requirements for safety, serviceability and durability are satisfied by following the rules given in this section in addition to the general rules given elsewhere. (2) The detailing of members should be consistent with the design
- [6] EN1992-1-1_2004，页 163，条款 9.6.1: (1) This clause refers to reinforced concrete walls with a length to thickness ratio of 4 or more and in which the reinforcement is taken into account in the strength analysis. The amount and proper detailing of reinforcement may be
- [7] DG_EN1992-1-1__-1-2，页 232，条款 : This method requires knowledge of the temperature distribution across the cross-section of the member. EN 1992-1-2 provides such profiles for slabs, beams and columns in Annex A for standard time-temperature relationships. The method may
- [8] EN1992-1-1 2004，页 14，条款 1.1.2, (1)P: (1)P Part 1-1 of Eurocode 2 gives a general basis for the design of structures in plain, reinforced and prestressed concrete made with normal and light weight aggregates together with specific rules for buildings. (2)P The following

## 22. 后张法预应力损失如何计算

- Excel 行号: 23
- 层级: Level 4 / 复杂场景与多参数耦合层

### 答案

根据欧洲规范 EN 1992-1-1 及其相关设计指南，后张法（post-tensioning）预应力损失的计算分为**瞬时损失**和**随时间变化的损失**两大类。以下是具体的计算步骤、适用公式及参数取值说明。

### 1. 瞬时损失 (Immediate losses)
瞬时损失 $\Delta P_i(x)$ 发生在张拉和锚固过程中或刚完成时，主要包括以下四项 [Ref-1]：

#### (1) 摩擦引起的损失 $\Delta P_\mu(x)$
后张法预应力筋在管道中张拉时，由于管道偏差和曲线线形会产生摩擦损失 [Ref-6]。
* **计算公式** [Ref-17]：
  $$ \Delta P_\mu(x) = P_{max} \left( 1 - e^{-\mu(\theta + kx)} \right) $$
* **参数说明与取值** [Ref-6]：
  * $P_{max}$：张拉端施加的最大张拉力。
  * $\theta$：从张拉端到计算截面距离 $x$ 内，预应力筋角度变化的总和（不考虑方向或符号）。
  * $\mu$：预应力筋与管道之间的摩擦系数。**优先采用欧洲技术批准（ETA）或制造商提供的数据**；若无数据，可查规范表 5.1 取值。
  * $k$：内部预应力筋的无意角度偏差（每单位长度）。若无 ETA 数据，一般取 $0.005 < k < 0.01 \text{ rad/m}$。
  * $x$：从张拉端沿预应力筋的距离。
  * **适用条件限制**：对于**外部预应力筋**（external tendons），由无意角度偏差（即 $k$ 项）引起的预应力损失可以忽略 [Ref-6]。

#### (2) 锚具回缩/滑移引起的损失 $\Delta P_{sl}$
* **计算说明**：规范正文未直接指定具体计算数值，要求从 ETA 文件或锚具制造商处获取回缩量，并在现场进行核实（特别是对于短构件，该损失可能起控制作用） [Ref-4], [Ref-21]。
* **指南参考参数**：设计指南指出，锚具回缩损失 $\Delta P$ 的计算依赖于以下参数 [Ref-21]：
  * $\delta$：锚具回缩量（draw-in）。
  * $E_p$：预应力筋弹性模量；$A_{ps}$：预应力筋截面积。
  * $m$：由摩擦引起的预应力变化率，可近似取 $m = P_0 \mu (\alpha + k)$（其中 $\alpha$ 为单位长度的角度偏差）。

#### (3) 混凝土弹性变形引起的损失 $\Delta P_{el}$
* **计算说明**：由于后张法通常是逐根张拉，先张拉的钢筋会因后续钢筋张拉导致混凝土发生弹性压缩而产生损失。计算方法遵循常规结构力学程序，根据混凝土在预应力作用下的弹性应变进行计算 [Ref-1], [Ref-4]。

#### (4) 短期松弛损失 $\Delta P_r$
* 发生在张拉过程与锚固完成与锚固完成之间的短暂时间段内的钢筋松弛损失 [Ref-1]。

---

### 2. 随时间变化的损失 (Time-dependent losses)
随时间变化的损失 $\Delta P_{c+s+r}(x)$ 是由混凝土的收缩、徐变以及预应力钢筋的长期松弛共同引起的 [Ref-1]。规范提供了一个考虑这三者相互作用的简化综合计算公式。

#### (1) 综合损失计算公式
* **计算公式 (5.46)** [Ref-15], [Ref-18]：
  $$ \Delta P_{c+s+r} = A_p \Delta \sigma_{p,c+s+r} = A_p \frac{\varepsilon_{cs} E_p + 0.8 \Delta \sigma_{pr} + \frac{E_p}{E_{cm}} \varphi(t, t_0) \sigma_{c,QP}}{1 + \frac{E_p}{E_{cm}} \frac{A_p}{A_c} \left(1 + \frac{A_c}{I_c} z_{cp}^2\right) \left[1 + 0.8 \varphi(t, t_0)\right]} $$
  *(注：证据原文中准永久组合下的混凝土应力符号识别为 $\sigma_{c,op}$，实际应为 $\sigma_{c,QP}$)*
* **参数说明** [Ref-15]：
  * $\varepsilon_{cs}$：混凝土收缩应变估计值的绝对值（按规范 3.1.4(6) 计算）。
  * $E_p, E_{cm}$：分别为预应力钢和混凝土的弹性模量。
  * $\varphi(t, t_0)$：混凝土徐变系数。
  * $\sigma_{c,QP}$：在初始预应力和准永久作用组合下，预应力筋重心处的混凝土应力。
  * $A_p, A_c$：预应力筋和混凝土的截面积；$I_c$：混凝土截面惯性矩；$z_{cp}$：预应力筋重心至混凝土截面重心的距离。
  * $\Delta \sigma_{pr}$：由于预应力钢松弛引起的应力变化绝对值。
  * **相互作用折减**：公式中的系数 **0.8** 是为了考虑混凝土徐变和收缩会降低钢筋应力，从而相应减少钢筋松弛损失的交互影响 [Ref-15]。

#### (2) 钢筋松弛损失 $\Delta \sigma_{pr}$ 的计算
松弛损失需根据预应力筋的松弛类别（Class 1, 2, 3）单独计算 [Ref-7]。
* **初始应力取值**：对于后张法，计算松弛时的初始应力 $\sigma_{pi}$ 取锚固后的初始预应力绝对值，即 $\sigma_{pi} = \sigma_{pm0}$ [Ref-3], [Ref-7]。
* **计算公式 (以 Class 1 普通松弛钢丝/钢绞线为例，公式 3.28)** [Ref-16]：
  $$ \frac{\Delta \sigma_{pr}}{\sigma_{pi}} = 5.39 \rho_{1000} e^{6.7\mu} \left(\frac{t}{1000}\right)^{0.75(1-\mu)} 10^{-5} $$
* **参数说明** [Ref-3], [Ref-7]：
  * $\rho_{1000}$：张拉后 1000 小时、平均温度 20°C 时的松弛损失百分比。若无测试证书，可假定：Class 1 取 8%，Class 2（低松弛）取 2.5%，Class 3（热轧及加工钢筋）取 4%。
  * $\mu = \sigma_{pi} / f_{pk}$，其中 $f_{pk}$ 为预应力钢抗拉强度特征值。
  * $t$：张拉后的时间（小时）。**长期（最终）松弛损失**可按 $t = 500,000$ 小时（约 57 年）进行估算 [Ref-3], [Ref-7]。
  * **温度限制**：若预应力筋经历热处理（如蒸汽养护）或温度超过 50°C，松弛损失对温度非常敏感，必须按规范 10.3.2.2 或附录 D 进行专门验证 [Ref-3], [Ref-7]。

---

### 3. 工程师应用注意事项
1. **数据优先级**：在计算摩擦损失（$\mu, k$）和锚具回缩量（$\delta$）时，规范强烈建议**优先采用欧洲技术批准（ETA）文件或制造商提供的测试数据**，而非直接使用规范给出的默认推荐值 [Ref-4], [Ref-6]。
2. **国家附录 (National Annex)**：计算初始张拉控制应力（决定 $\sigma_{pi}$ 的上限）时，涉及参数 $k_7$（推荐 0.75）和 $k_8$（推荐 0.85），必须核查项目所在国的国家附录是否有修改 [Ref-1]。
3. **分阶段计算**：如果需要对不同时间区间（阶段）进行更高精度的松弛损失计算，应参考规范附录 D 的详细计算方法 [Ref-3], [Ref-7]。

### 来源

- [1] EN1992-1-1_2004，页 77，条款 5.10.3, (1)P: (1)P At a given time t and distance x (or arc length) from the active end of the tendon the mean prestress force $P _ { \mathrm { m , t } } ( x )$ is equal to the maximum force $P _ { \mathrm { { m a x } } }$ imposed at the active end,
- [2] EN1992-1-1_2004，页 78，条款 5.10.4: (1) The following losses occurring during pre-tensioning should be considered: (i) during the stressing process: loss due to friction at the bends (in the case of curved wires or strands) and losses due to wedge draw-in of the anchorage
- [3] EN1992-1-1_2004，页 42，条款 3.3.2, (1)P: (7) The relaxation loss may be obtained from the manufacturers test certificates or defined as the percentage ratio of the variation of the prestressing stress over the initial prestressing stress, should be determined by applying one of
- [4] DG_EN1992-1-1__-1-2，页 221，条款 : The designer’s attention is drawn to the need to allow for losses of prestress when calculating the design forces in tendons at the various stages considered in the design. The causes of these losses are listed in EN 1992-1-1. Because of
- [5] EN1992-1-1 2004，页 77，条款 5.10.3, (1)P: (1)P At a given time $t$ and distance $\pmb { \times }$ (or arc length) from the active end of the tendon the mean prestress force $P _ { \mathrm { m , t } } ( x )$ is equal to the maximum force $P _ { \mathrm { { m a x } } }$ imposed at
- [6] EN1992-1-1 2004，页 79，条款 5.10.5.2: (1) The losses due to friction $\Delta P _ { \mu } ( x )$ in post-tensioned tendons may be estimated from: where: $\theta$ is the sum of the angular displacements over a distance x (irrespective of direction or sign) $\mu$ is the
- [7] EN1992-1-1 2004，页 42，条款 3.3.2, (1)P: (1)P The properties of prestressing steel are given in EN 10138, Parts 2 to 4 or European Technical Approval. (2)P The prestressing tendons (wires, strands and bars) shall be classified according to: (i) Strength, denoting the value of the
- [8] EN1992-1-1_2004，页 75，条款 5.10.1, (1)P: (1)P The prestress considered in this Standard is that applied to the concrete by stressed tendons. (2) The effects of prestressing may be considered as an action or a resistance caused by prestrain and precurvature. The bearing capacity

## 23. 预应力在各类极限状态下的影响是什么

- Excel 行号: 24
- 层级: Level 4 / 复杂场景与多参数耦合层

### 答案

基于欧洲规范 EN 1992-1-1 及其相关设计指南，预应力在承载能力极限状态（ULS）和正常使用极限状态（SLS）下的影响及设计考虑存在显著差异。以下为具体分类说明：

### 一、 承载能力极限状态 (ULS) 下的影响与设计
1. **分项系数取值**：在大多数情况下，预应力是有利影响，ULS 验证时应使用有利分项系数 $\gamma_{p,fav}$ [Ref-1, Ref-4, Ref-6]。EN 1992-1-1 推荐 $\gamma_{p,fav} = 1.0$，不利分项系数 $\gamma_{p,unfav} = 1.3$ [Ref-1, Ref-6]。
   *注意：英国国家附录 (UK NA) 将其修改为 $\gamma_{p,fav} = 0.9$ 和 $\gamma_{p,unfav} = 1.1$ [Ref-1, Ref-5]。*
2. **特殊情况的 ULS 验证**：
   - 对于外部预应力的整体稳定性极限状态，若预应力增加会产生不利影响，应使用 $\gamma_{p,unfav}$（推荐值 1.3）[Ref-6, Ref-16]。
   - 对于局部效应（如锚固区），也应使用 $\gamma_{p,unfav}$（推荐值 1.2）[Ref-6, Ref-16]。
3. **截面设计中的应变计算**：ULS 下需考虑初始应变 $\varepsilon_{p0}$ 乘以分项系数，并加上应变增量 $\Delta\varepsilon_p$ [Ref-1, Ref-5]。
   - **有粘结预应力筋**：应变增量等于预应力筋水平处混凝土的应变增量 [Ref-1, Ref-5]。
   - **无粘结和外部预应力筋**：应变增量需基于构件变形计算，或假定应力增加 100 N/mm² [Ref-1, Ref-5]。若使用平均属性计算变形，应力增量需乘以 $\gamma_{\Delta p}$（有利取 0.8，不利取 1.2）；若使用未开裂截面进行线性分析，则取 $\gamma_{\Delta p} = 1.0$ [Ref-1, Ref-5]。

### 二、 正常使用极限状态 (SLS) 下的影响与设计
1. **预应力特征值上下限**：SLS 下荷载和材料属性的分项系数通常为 1.0 [Ref-7, Ref-13, Ref-16]。预应力采用上限 ($r_{sup}$) 或下限 ($r_{inf}$) 特征值，取对设计更不利的值 [Ref-5]。
   - 先张或无粘结筋：上限 1.05，.05，下限 0.95（乘以平均值）[Ref-2, Ref-5]。
   - 后张有粘结筋：上限 1.1，下限 0.9 [Ref-2, Ref-5]。
   - *注意：英国国家附录 (UK NA) 简化采用单一值 1.0 [Ref-2, Ref-5]；对于受剪设计，EN 和 UK 均取 1.0 [Ref-2]。*
2. **裂缝控制**：SLS 需考虑特征、频遇和准永久三种荷载组合 [Ref-5, Ref-7]。根据暴露类别和预应力筋类型，裂缝宽度限制如下 [Ref-3]：
   - **无粘结筋**（准永久荷载）：所有暴露类别限制为 0.3 mm [Ref-3]。
   - **有粘结筋**（频遇荷载）：X0、XC1 及 XC2~XC4 类别限制为 0.2 mm；XD、XS 类别要求消压 (Decompression) [Ref-3]。
   - **有粘结筋**（准永久荷载）：XC2~XC4 类别要求消压 [Ref-3]。
3. **混凝土应力限制与徐变**：
   - 在侵蚀性环境（XD, XF, XS）中，建议将 SLS 下的混凝土压应力限制在 $0.6 f_{ck}$，或采取增加保护层/横向约束等措施 [Ref-13]。
   - 若准永久组合下压应力超过 $0.45 f_{ck}$，应考虑非线性徐变的影响 [Ref-13]。

### 三、 疲劳及其他时间依存效应
1. **疲劳极限状态**：疲劳验证时，预应力的有利分项系数 $\gamma_{p,fav}$ 推荐值同样可取 1.0 [Ref-4, Ref-6]。
2. **徐变、收缩与温度效应**：
   - **SLS**：必须考虑徐变和收缩的影响 [Ref-9, Ref-10]。徐变效应应在准永久组合下评估，通常使用永久荷载和预应力平均值 [Ref-9, Ref-10]。温度效应也应在 SLS 中予以考虑 [Ref-10]。
   - **ULS**：仅当这些时间依存效应显著时（例如二阶效应重要的稳定性验证）才需考虑；若构件具有足够的延性和转动能力，通常可忽略 [Ref-9, Ref-10]。

### 四、 依据位置
- [Ref-1] DG_EN1992-1-1__-1-2, 11.5.1. Ultimate limit state, pp. 216-217
- [Ref-2] DG_EN1992-1-1__-1-2, Table 11.6, pp. 216-217
- [Ref-3] DG_EN1992-1-1__-1-2, Table 11.7, pp. 216-217
- [Ref-4] EN1992-1-1 2004, 2.4.2.2, p. 23
- [Ref-5] DG_EN1992-1-1__-1-2, 11.5. Design of sections for flexure and axial load, pp. 216-217
- [Ref-6] EN1992-1-1_2004, 2.4.2.2, pp. 23-24
- [Ref-7] DG_EN1992-1-1__-1-2, 8.1. General, pp. 139-140
- [Ref-9] EN1992-1-1 2004, 2.3.2.2, p. 22
- [Ref-10] EN1992-1-1_2004, 2.3.1.1~2.3.1.3, pp. 20-23
- [Ref-13] DG_EN1992-1-1__-1-2, Serviceability limit states, pp. 139-192
- [Ref-16] EN199 EN1992-1-1_2004, 2.4.2.1~2.4.2.3, pp. 23-25

### 来源

- [1] DG_EN1992-1-1__-1-2，页 216，条款 : EN 1992-1-1 specifies two partial safety factors for prestress when considering overall analysis and the design of sections: $\gamma _ { \mathrm { p , f a v } } = 1 . 0$ and $\gamma _ { \mathrm { p , u n f a v } } = 1 . 3$ . However, the
- [2] DG_EN1992-1-1__-1-2，页 216，条款 Table 11.6: Table 11.6. Partial factors to be used for prestress <table><tr><td rowspan="2" colspan="2"></td><td colspan="4">Partial factors</td></tr><tr><td colspan="2">Serviceability limit state</td><td colspan="2">Ultimate limit
- [3] DG_EN1992-1-1__-1-2，页 216，条款 Table 11.7: Table 11.7. Criteria for controlling cracking <table><tr><td rowspan="2">Exposure class</td><td rowspan="2">Unbonded tendons: quasi-permanent loads</td><td colspan="2">Bonded tendons</td></tr><tr><td>Frequent loads</td><td>Quasi-permanent
- [4] EN1992-1-1 2004，页 23，条款 2.4.2.2: (1) Prestress in most situations is intended to be favourable and for the ultimate limit state verification the value of $\mathcal { W } , \mathfrak { f a v }$ should be used. The design value of prestress may be based on the mean value of
- [5] DG_EN1992-1-1__-1-2，页 216，条款 : EN 1992-1-1 specifies two partial safety factors for prestress when considering overall analysis and the design of sections: $\gamma _ { \mathrm { p , f a v } } = 1 . 0$ and $\gamma _ { \mathrm { p , u n f a v } } = 1 . 3$ . However, the
- [6] EN1992-1-1_2004，页 23，条款 2.4.2.2: (1) Prestress in most situations is intended to be favourable and for the ultimate limit state verification the value of $\mathcal { W } , \mathfrak { f a v }$ should be used. The design value of prestress may be based on the mean value of
- [7] DG_EN1992-1-1__-1-2，页 139，条款 : EN 1990 (clause 6.5.3) defines three combinations of actions which may need to be considered when designing for a serviceability limit state. These are: Characteristic combination: • Frequent combination: Quasi-permanent combination: It
- [8] EN1992-1-1 2004，页 148，条款 : values, depending on the design situation: or $\begin{array} { r } { l _ { \mathsf { p t } 1 } = 0 , 8 \ l _ { \mathsf { p t } } } \\ { \quad } \\ { l _ { \mathsf { p t } 2 } = 1 , 2 \ l _ { \mathsf { p t } } } \end{array}$ Note: Normally

## 24. 剪应力一般验证程序是怎样的

- Excel 行号: 25
- 层级: Level 2 / 构件极限状态计算层

### 答案

根据欧洲规范 EN 1992-1-1（混凝土结构设计），剪应力（剪力）的验证程序主要分为**一般剪切（梁、板等构件）**和**冲切（板柱节点、基础）** 两类。以下是基于规范条文整理的标准化验证步骤：

### 一、 一般剪切验证程序（梁、板等构件）
一般剪切验证基于桁架模型，核心是对比设计剪力与构件的抗剪承载力。

**1. 确定设计剪力 $V_{Ed}$**
计算由外部荷载和预应力（粘结或无粘结）在目标截面引起的设计剪力 $V_{Ed}$ [Ref-1, Ref-6]。

**2. 验算无抗剪钢筋的抗剪承载力 $V_{Rd,c}$**
*   **若 $V_{Ed} \le V_{Rd,c}$**：理论上无需通过计算配置抗剪钢筋，但仍需按规范第9.2.2节配置**最小抗剪钢筋** [Ref-1, Ref-6]。
    *   *豁免条件*：对于能够横向重分布荷载的板（如实心板、肋形板或空心板），或不显著影响结构整体抗力和稳定性的次要构件（如跨度 $\le 2\text{ m}$ 的过梁），可省略最小抗剪钢筋 [Ref-1, Ref-6]。
*   **若 $V_{Ed} > V_{Rd,c}$**：必须配置足够的抗剪钢筋，进入步骤4 [Ref-1, Ref-6]。

**3. 验算截面最大抗剪承载力 $V_{Rd,max}$（防止混凝土压杆压碎）**
在构件的任何部位，设计剪力（扣除倾斜弦杆的贡献后，即 $V_{Ed} - V_{ccd} - V_{td}$）均不得超过由混凝土压杆压碎控制的极限值 $V_{Rd,max}$ [Ref-1, Ref-6]。

**4. 计算所需抗剪钢筋**
当需要配置抗剪钢筋时，构件的总抗剪承载力 $V_{Rd}$ 应满足 $V_{Ed} \le V_{Rd}$ [Ref-1, Ref-6]。
*   总承载力公式：$V_{Rd} = V_{Rd,s} + V_{ccd} + V_{td}$ [Ref-2, Ref-6]。
*   抗剪钢筋提供的承载力（公式6.8）：$V_{Rd,s} = \frac{A_{sw}}{s} z f_{ywd} \cot\theta$ [Ref-3]。
    *(注：$A_{sw}$ 为抗剪钢筋截面积，$s$ 为间距，$z$ 为内力臂，$f_{ywd}$ 为抗剪钢筋设计屈服强度，$\theta$ 为混凝土压杆倾角)*。

**5. 纵向钢筋附加拉力验算**
纵向受拉钢筋必须具备足够的锚固和截面积，以抵抗由剪力引起的附加拉力 [Ref-6]。

**6. 支座附近的特殊规定**
对于主要承受均布荷载的构件，距支座边缘小于有效高度 $d$ 的范围内无需验算设计剪力，但抗剪钢筋必须延伸至支座，且支座边缘处的剪力仍不得超过 $V_{Rd,max}$ [Ref-6]。

---

### 二、 冲切验证程序（板柱节点、基础）
冲切验证主要针对集中荷载或支座反力作用在相对较小区域的情况，验证基于控制截面上的剪应力进行。

**1. 确定控制截面**
验证应在**柱周边（或加载区域周边）**以及**基本控制周长 $u_1$**（通常距加载区域 $2.0d$）处进行 [Ref-4, Ref-8, Ref-10, Ref-14]。

**2. 计算设计冲切剪应力 $v_{Ed}$**
*   若支座反力对控制周长存在偏心，最大剪应力需乘以放大系数 $\beta$。
*   计算公式（公式6.38）：$v_{Ed} = \beta \frac{V_{Ed}}{u_i d}$ [Ref-10, Ref-17]。

**3. 验算最大冲切剪应力（防局部压碎）**
在柱周边或加载区域周边，设计冲切剪应力不得超过最大限值：$v_{Ed} \le v_{Rd,max}$ [Ref-4, Ref-10]。

**4. 验算是否需要冲切钢筋**
*   **若 $v_{Ed} \le v_{Rd,c}$**（无冲切钢筋的板抗力）：无需配置冲切钢筋 [Ref-4, Ref-10]。
*   **若 $v_{Ed} > v_{Rd,c}$**：必须配置冲切钢筋，并需向外扩展计算，找到不再需要冲切钢筋需要冲切钢筋的外围控制周长 $u_{out,ef}$ [Ref-4, Ref-10, Ref-14]。

---

### 三、 适用条件与注意事项提醒
1. **国家附录（National Annex）参数**：规范中涉及的诸多关键参数（如 $C_{Rd,c}$、$v_{min}$、$k_1$、$\cot\theta$ 的限值范围等）均允许各国自行规定。工程师在实际计算时，**必须查阅项目所在国的国家附录**以获取准确数值 [Ref-13, Ref-14]。
2. **倾斜弦杆构件**：对于具有倾斜受压或受拉弦杆的变截面构件，必须计算并计入混凝土受压区剪力分量 $V_{ccd}$ 和受拉钢筋剪力分量 $V_{td}$ [Ref-1, Ref-6]。
3. **底部加载情况**：若荷载作用在截面底部附近（如牛腿或悬挂荷载），除常规抗剪钢筋外，还需配置足够的竖向钢筋将荷载直接传递至截面顶部 [Ref-6]。

### 四、 依据位置
*   **一般剪切验证程序**：EN 1992-1-1:2004, 第6.2.1节 (1)P~(9) [Ref-1, Ref-6]；第6.2.3节 公式(6.8) [Ref-3]。
*   **冲切验证程序**：EN 1992-1-1:2004, 第6.4.1节 [Ref-8]；第6.4.3节 (1)P~(3) 及公式(6.38) [Ref-4, Ref-10, Ref-17]。
*   **参数与国家附录说明**：EN 1992-1-1:2004, 第6.2.2节及6.4.4节 [Ref-13, Ref-14]。

### 来源

- [1] EN1992-1-1_2004，页 84，条款 6.2.1, (1)P: (1)P For the verification of the shear resistance the following symbols are defined: $V _ { \sf R d , c }$ is the design shear resistance of the member without shear reinforcement. $V _ { \sf R d , s }$ is the design value of the shear
- [2] EN1992-1-1 2004，页 84，条款 : $$ V _ { \mathrm { R d } } = V _ { \mathrm { R d , s } } + V _ { \mathrm { c c d } } + V _ { \mathrm { t d } } $$
- [3] EN1992-1-1_2004，页 88，条款 : $$ V _ { \mathrm { R d , \thinspace s } } = \frac { A _ { \mathrm { s w } } } { s } z f _ { \mathrm { y w d } } \thinspace { \sf c o t } \theta\tag{6.8} $$
- [4] EN1992-1-1_2004，页 101，条款 6.4.3, (1)P: (1)P The design procedure for punching shear is based on checks at the face of the column and at the basic control perimeter $u _ { 1 }$ . If shear reinforcement is required a further perimeter $u _ { \mathrm { o u t , } }$ ef (see figure
- [5] DG_EN1992-1-1__-1-2，页 237，条款 : punching shear 98–106 basic control perimeter 98–9 design shear force 99–101 enhancement factor 102 resistance of slabs without shear reinforcement 102–3 reinforcement 103–6, 198 radius of gyration 111 rectangular column sections, design
- [6] EN1992-1-1 2004，页 84，条款 6.2.1, (1)P: (1)P For the verification of the shear resistance the following symbols are defined: $V _ { \sf R d , c }$ is the design shear resistance of the member without shear reinforcement. $V _ { \sf R d , s }$ is the design value of the shear
- [7] EN1992-1-1_2004，页 2，条款 : 4.4.1 Concrete cover 4.4.1.1 General 4.4.1.2 Minimum cover, cmin 4.4.1.3 Allowance in design for tolerance 5. Structural analysis 5.1 General 5.1.1 General requirements 5.1.2 Special requirements for foundations 5.1.3 Load cases and
- [8] EN1992-1-1_2004，页 97，条款 6.4.1, (1)P: (1)P The rules in this Section complement those given in 6.2 and cover punching shear in solid slabs, waffle slabs with solid areas over columns, and foundations. (2)P Punching shear can result from a concentrated load or reaction acting

## 25. 单向板的设计步骤包括哪些

- Excel 行号: 26
- 层级: Level 2 / 构件极限状态计算层

### 答案

基于欧洲规范 EN 1992-192-1-1 及其相关指南，单向板（One-way spanning slab）的设计步骤可系统归纳为结构判定、内力分析、极限状态验算及构造细部设计等核心环节。以下为可直接使用的设计步骤及核查要点：

### 1. 结构判定与建模
*   **单向板界定**：对于主要承受均布荷载的板，若满足以下任一条件，可视为单向板进行设计 [Ref-3]：
    1. 具有两个自由（无支撑）且大致平行的边缘；
    2. 为四边支撑的矩形板的中心部分，且长跨与短跨之比大于 2。

### 2. 荷载布置与内力分析
*   **荷载组合布置**：需考虑交替跨加载（设计可变荷载+永久荷载）与相邻跨加载等不同布置方式，以获取弯矩和剪力的包络图 [Ref-22]。
*   **支座弯矩简化与调整**（无论采用何种分析方法均适用） [Ref-5], [Ref-7]：
    *   **无转动约束支座**（如墙体）：连续板的设计支座弯矩可减小 $F_{Ed,supp} t / 8$（$F_{Ed,supp}$ 为支座反力，$t$ 为支座宽度）。
    *   **整体浇筑支座**：临界设计弯矩可取支座边缘处的弯矩。
    *   **刚性支座**：支座边缘的设计弯矩不得小于假定完全固定时计算值的 65%。
*   **指南简化计算（可选）**：若满足以下条件，可直接使用指南提供的弯矩和剪力系数表（如指南表3.3）进行计算，但**不允许**进行弯矩重分布 [Ref-18], [Ref-23]：
    1. 特征可变荷载不超过特征永久荷载；
    2. 荷载主要为均布且跨越三个或更多跨；
    3. 跨度变化不超过最长跨的 15%；
    4. 端柱与板的刚度比不超过 1.0。

### 3. 承载能力极限状态 (ULS) 设计
*   **受弯配筋计算**：根据内力包络图计算主受力方向的受弯钢筋面积。对于脆性破坏风险较小的板，最小配筋面积 $A_{s,min}$ 可取 ULS 验算所需面积的 1.2 倍 [Ref-4], [Ref-12]。
*   **塑性分析限制**：若采用塑性分析（弯矩重分布），必须验证转动能力，或满足以下**免算转动能力**的条件 [Ref-6]：
    1. 受压区高度限制：$x_u/d \le 0.25$（混凝土 $\le$ C50/60）或 $x_u/d \le 0.15$（混凝土 $\ge$ C55/67）；
    2. 钢筋必须为 B 级或 C 级（不推荐使用 A 级）；
    3. 中间支座弯矩与跨中弯矩之比在 0.5 到 2 之间。
    *(注：若进行显式转动能力验算，屈服铰区域的 $x_u/d$ 不得超过 0.45 或 0.35 [Ref-1], [Ref-2]。)*

### 4. 正常使用极限状态 (SLS) 验算
*   **挠度控制**：通常可通过限制**跨高比（span/effective depth）** 来免除详细的挠度计算。根据规范表 7.4N，无轴压钢筋混凝土单向板的基本跨高比系数 $K$ 为 [Ref-9]：
    *   简支单向板：$K = 1.0$
    *   连续单向板端跨：$K = 1.3$
    *   连续单向板内部跨：$K = 1.5$
    *(注：需根据实际配筋率 $\rho$ 查表获取具体限值，并乘以 $K$ 值。)*

### 5. 构造与细部设计 (Detailing)
*   **横向分布钢筋**：单向板必须提供不小于主受力钢筋面积 **20%** 的次要横向钢筋。但在支座附近若无横向弯矩，则顶部主筋无需配置横向钢筋 [Ref-4], [Ref-12]。
*   **钢筋间距限制**：需符合国家附录（NDP）规定。规范推荐的最大间距 $s_{max,slabs}$ 为 [Ref-4], [Ref-12]：
    *   一般区域：主筋 $3h \le 400\text{ mm}$，次筋 $3.5h \le 450\text50\text{ mm}$（$h$ 为板厚）；
    *   集中荷载或最大弯矩区域：主筋 $2h \le 250\text{ mm}$，次筋 $3h \le 400\text{ mm}$。
*   **支座锚固与截断** [Ref-4], [Ref-12]：
    *   **简支板**：至少一半的计算跨中钢筋应延伸至支座并按规范锚固。
    *   **部分固定边缘**（分析中未考虑固定作用时）：顶部钢筋需能承受相邻跨最大弯矩的至少 **25%**（端支座可减至 **15%**），并从支座边缘延伸至少 **0.2 倍**相邻跨长。
*   **自由边缘**：沿无支撑的自由边缘，必须配置纵向和横向的边缘钢筋（U型或闭合箍筋形式） [Ref-4], [Ref-12]。

### 6. 防火设计 (如适用)
*   **单向板界定**：若板不满足四边支撑条件，在防火设计中必须按单向板处理 [Ref-8]。
*   **连续板支座配筋要求**：对于连续单向板，若出现以下情况之一，中间支座处必须提供至少 **0.5% $A_c$** 的顶部钢筋 [Ref-8]：
    1. 使用冷加工钢筋；
    2. 端支座无固定或未按照 EN 1992-1-1 进行细部设计；
    3. 荷载效应无法在横向进行分布。
*   **截面尺寸与保护层**：需根据目标耐火极限（如 R60, R90），查规范表格确定最小楼板厚度及钢筋轴线距离（保护层厚度 + 钢筋半径），以满足承载力(R)和隔热性(I)要求 [Ref-11]。

---

### ⚠️ 工程师注意事项（适用条件与国家附录）
1. **国家附录 (NDP) 差异**：钢筋最大间距限值 [Ref-4]、塑性分析的基本允许转动角 $\theta_{pl,d}$ [Ref-1] 等参数，各国国家附录可能采用与规范推荐值不同的数值，设计时必须查阅项目所在国的 National Annex。
2. **支撑构件设计**：在评估支撑单向连续板的构件（如梁、墙）上的荷载时，可假定支座无转动约束；但在设计支撑构件（如柱子）本身时，必须考虑板连续性带来的弯矩传递效应 [Ref-5], [Ref-7]。
3. **指南参考说明**：上述步骤 2 中提及的“指南表 3.3 弯矩系数”属于非矛盾性补充信息（指南 DG_EN1992-1-1），可大幅简化手算过程，但前提是必须严格满足其 4 项前置假设条件 [Ref-18], [Ref-23]。

### 来源

- [1] EN1992-1-1_2004，页 62，条款 5.6.3: (1) The simplified procedure for continuous beams and continuous one way spanning slabs is based on the rotation capacity of beam/slab zones over a length of approximately 1,2 times the depth of section. It is assumed that these zones
- [2] EN1992-1-1 2004，页 62，条款 5.6.3: (1) The simplified procedure for continuous beams and continuous one way spanning slabs is based on the rotation capacity of beam/slab zones over a length of approximately 1,2 times the depth of section. It is assumed that these zones
- [3] EN1992-1-1 2004，页 57，条款 5.3.1, (1)P: (1)P The elements of a structure are classified, by consideration of their nature and function, as beams, columns, slabs, walls, plates, arches, shells etc. Rules are provided for the analysis of the commoner of these elements and of
- [4] EN1992-1-1_2004，页 158，条款 9.3.1.1, 9.3.1.2: (1) For the minimum and the maximum steel percentages in the main direction 9.2.1.1 (1) and (3) apply. Note: In addition to Note 2 of 9.2.1.1 (1), for slabs where the risk of brittle failure is small, $A _ { \mathsf { s } , \mathsf { m i n
- [5] DG_EN1992-1-1__-1-2，页 61，条款 : For the design of beams, the bending moment coefficients given in Fig. 3.20 or Table 3.3 may be used, noting the conditions to be complied with, which are discussed in Section 3.8.1. EN 1992-1-1 permits the following simplifications
- [6] EN1992-1-1_2004，页 61，条款 5.6.1, (1)P: (1)P Methods based on plastic analysis shall only be used for the check at ULS. (2)P The ductility of the critical sections shall be sufficient for the envisaged mechanism to be formed. (3)P The plastic analysis should be based either on
- [7] DG_EN1992-1-1__-1-2，页 61，条款 : EN 1992-1-1 permits the following simplifications regardless of the method of analysis used: (1) At a support assumed to offer no restraint to rotation (e.g. over walls), a beam or a slab which is continuous over it may be designed for a
- [8] DG_EN1992-1-1__-1-2，页 232，条款 : The data for two-way spanning slabs are applicable only to slabs supported on all four edges. If this is not met, the slab should be treated as one-way spanning. The thickness of the slab for continuous slabs is the same as for simply

## 26. 单向板构造配筋有什么规定

- Excel 行号: 27
- 层级: Level 3 / 构造规定与抗震补充层

### 答案

根据欧洲规范 EN 1992-1-1（Eurocode 2）的规定，单向实心板（one-way spanning solid slabs）的构造配筋（detailing reinforcement）在受弯、支座锚固、边缘构造及抗剪等方面有明确的要求。以下为整合后的具体规定：

### 1. 受弯配筋与钢筋间距
*   **主方向配筋率**：主方向的最小和最大配筋率需符合一般受弯构件的规定。但对于脆性破坏风险较小的板，最小配筋面积 $A_{s,min}$ 可取承载能力极限状态（ULS）计算所需面积的 1.2 倍 [Ref-1]。
*   **横向分布筋（次要配筋）**：单向板必须配置次要横向配筋，其截面积不应小于主筋面积的 **20%** [Ref-1]。但在支座附近区域，若不存在横向弯矩，则主顶部钢筋无需配置横向分布筋 [Ref-1]。
*   **钢筋最大间距**：钢筋间距不应超过 $s_{max,slabs}$，规范推荐值如下（$h$ $h$ 为板总厚度）[Ref-1]：
    *   **一般区域**：主筋间距 $\le 3h$ 且 $\le 400\text{ mm}$；次要筋间距 $\le 3.5h$ 且 $\le 450\text{ mm}$。
    *   **集中荷载或最大弯矩区域**：主筋间距 $\le 2h$ 且 $\le 250\text{ mm}$；次要筋间距 $\le 3h$ 且 $\le 400\text{ mm}$。

### 2. 支座与边缘构造配筋
*   **简支支座锚固**：在简支板中，至少 **一半** 的跨中计算受拉钢筋应延伸至支座，并按规范 8.4.4 节的要求进行锚固 [Ref-1]。
*   **未考虑固结的支座（部分固结）**：若板边缘存在部分固结但在结构分析中未予考虑，顶部构造钢筋应能承受相邻跨最大弯矩的至少 **25%**（在端支座处该比例可降至 **15%**）[Ref-1]。该钢筋应从支座边缘向跨内延伸至少 **0.2 倍** 相邻跨长，在内部支座处应连续，在端支座处应可靠锚固 [Ref-1]。
*   **板角防翘起**：若支座处的构造布置限制了板角的翘起（lifting），应配置合适的防翘起钢筋 [Ref-1]。
*   **自由边缘配筋**：沿无支撑的自由边缘，板通常应配置纵向和横向边缘钢筋（板的正常受力配筋可兼作边缘配筋）[Ref-1]。

### 3. 抗剪配筋构造要求
*   **最小厚度限制**：若板需要配置抗剪钢筋，板的总厚度至少应为 **200 mm** [Ref-3]。
*   **抗剪钢筋形式**：当剪力设计值 $|V_{Ed}| \le 1/3 V_{Rd,max}$ 时，抗剪钢筋可全部采用弯起钢筋或抗剪钢筋组件 [Ref-3]。
*   **抗剪钢筋间距**：抗剪钢筋（如箍筋）的最大横向间距不应超过 **1.5d**（$d$ 为有效高度）[Ref-3]。

### 4. 塑性分析附加要求（如适用）
*   若连续单向板采用塑性分析（考虑塑性铰转动能力），在塑性铰区域，受压区高度与有效高度之比 $x_u/d$ 必须满足：混凝土强度等级 $\le$ C50/60 时不超过 **0.45**；$\ge$ C55/67 时不超过 **0.35** [Ref-9]。

---

### ⚠️ 适用条件与注意事项
1.  **适用范围**：上述第 9.3 节的规定适用于单向和双向实心板，前提是板的宽度 $b$ 和有效跨度 $l_{eff}$ 均不小于 $5h$ [Ref-10]。
2.  **国家附录（National Annex）差异**：钢筋最大间距 $s_{max,slabs}$ 的具体限值可能因国家而异，**必须查阅项目所在国的国家附录**以确认是否采用了规范推荐值或进行了修改 [Ref-1]。
3.  **预制叠合板**：对于带有叠合层（topping）的预制板系统，弯曲和横向分布配筋可完全布置在叠合层内，但构造细节必须与结构分析模型（如假定双向受力）保持一致 [Ref-5]。

### 依据位置
*   [Ref-1] EN 1992-1-1:2004, 章节 9.3.1.1, 9.3.1.2, 9.3.1.3, 9.3.1.4 (页码 158-159)
*   [Ref-3] EN 1992-1-1:2004, 章节 9.3.2 (页码 159-160)
*   [Ref-5] EN 1992-1-1:2004, 章节 10.9.3 (页码 175-177)
*   [Ref-9] EN 1992-1-1:2004, 章节 5.6.3 (页码 62-63)
*   [Ref-10] EN 1992-1-1:2004, 章节 9.3 (页码3 (页码 158)

### 来源

- [1] EN1992-1-1_2004，页 158，条款 9.3.1.1, 9.3.1.2: (1) For the minimum and the maximum steel percentages in the main direction 9.2.1.1 (1) and (3) apply. Note: In addition to Note 2 of 9.2.1.1 (1), for slabs where the risk of brittle failure is small, $A _ { \mathsf { s } , \mathsf { m i n
- [2] DG_EN1992-1-1__-1-2，页 209，条款 : Concentration of reinforcement over the columns will generally be required to meet the serviceability requirements. In the absence of rigorous calculations, top reinforcement with an area of 0.5At, should be placed in a width equal to the
- [3] EN1992-1-1_2004，页 159，条款 9.3.2: (1) A slab in which shear reinforcement is provided should have a depth of at least 200 mm. (2) In detailing the shear reinforcement, the minimum value and definition of reinforcement ratio in 9.2.2 apply, unless modified by the following.
- [4] EN1992-1-1_2004，页 158，条款 9.3.1.1, 9.3.1.2: (1) For the minimum and the maximum steel percentages in the main direction 9.2.1.1 (1) and (3) apply. Note: In addition to Note 2 of 9.2.1.1 (1), for slabs where the risk of brittle failure is small, $A _ { \mathsf { s } , \mathsf { m i n
- [5] EN1992-1-1_2004，页 175，条款 10.9.3, (1)P: (9) Transverse reinforcement for bending and other action effects may lie entirely within the topping. The detailing should be consistent with the structural model, e.g. if two-way spanning is assumed. (10) Webs or ribs in isolated slab
- [6] EN1992-1-1 2004，页 158，条款 9.3.1.1: (1) For the minimum and the maximum steel percentages in the main direction 9.2.1.1 (1) and (3) apply. Note: In addition to Note 2 of 9.2.1.1 (1), for slabs where the risk of brittle failure is small, $A _ { \mathsf { s } , \mathsf { m i n
- [7] DG_EN1992-1-1__-1-2，页 230，条款 : Section 5 of EN 1992-1-2 sets out minimum dimensions and axis distances (cover plus half the diameter of the reinforcement bar) for different types of structural element for fire exposure periods of 30, 60, 90, 120, 180 and 240 min. Some
- [8] DG_EN1992-1-1__-1-2，页 232，条款 : The data for two-way spanning slabs are applicable only to slabs supported on all four edges. If this is not met, the slab should be treated as one-way spanning. The thickness of the slab for continuous slabs is the same as for simply

## 27. 单向板分布筋的配置有什么规定

- Excel 行号: 28
- 层级: Level 3 / 构造规定与抗震补充层

### 答案

根据欧洲规范 EN 1992-1-1，单向板分布筋（次要横向钢筋）的配置主要受配筋量比例、最大间距以及支座区域受力状态的限制。

### 依据与说明

1. **配筋量要求**
   单向板必须配置次要横向钢筋（分布筋），其截面积不应小于主要受力钢筋（主筋）截面积的 20% [Ref-1]。

2. **支座区域的豁免条件**
   在靠近支座的区域，如果经分析确认不存在横向弯矩，则不需要为顶部的主要受力钢筋配置横向分布筋 [Ref-1]。

3. **最大间距限制**
   分布筋的间距不应超过规定的最大间距 $s_{\mathrm{max,slabs}}$ [Ref-1]。规范给出的推荐值如下：
   - **一般区域**：分布筋的最大间距为 $3.5h$ 且不超过 $450\text{ mm}$（其中 $h$ 为板的总厚度） [Ref-1]。
   - **集中荷载区域或最大弯矩区域**：分布筋的最大间距要求更严，为 $3h$ 且不超过 $400\text{ mm}$ [Ref-1]。

### 注意事项

- **国家附录（National Annex）差异**：规范中关于最大间距 $s_{\mathrm{max,slabs}}$ 的数值为推荐值。具体工程项目所在国家的国家附录可能会对该限值进行修改，设计时必须核查并采用当地国家附录中规定的值 [Ref-1]。
- **主筋规定的关联影响**：主方向钢筋的最小和最大配筋率需满足规范第 9.2.1.1 节的规定 [Ref-1]。由于分布筋面积是按主筋面积的 20% 计算，因此主筋的计算结果将直接决定分布筋的绝对配置量。

### 依据位置
- 《EN 1992-1-1:2004》第 9.3.1.1 节第 (2)、(3) 款，第 158-159 页 [Ref-1]。

### 来源

- [1] EN1992-1-1_2004，页 158，条款 9.3.1.1: (1) For the minimum and the maximum steel percentages in the main direction 9.2.1.1 (1) and (3) apply. Note: In addition to Note 2 of 9.2.1.1 (1), for slabs where the risk of brittle failure is small, $A _ { \mathsf { s } , \mathsf { m i n
- [2] EN1992-1-1_2004，页 158，条款 9.3.1.1, 9.3.1.2: (1) For the minimum and the maximum steel percentages in the main direction 9.2.1.1 (1) and (3) apply. Note: In addition to Note 2 of 9.2.1.1 (1), for slabs where the risk of brittle failure is small, $A _ { \mathsf { s } , \mathsf { m i n
- [3] EN1992-1-1 2004，页 158，条款 9.3.1.1: (1) For the minimum and the maximum steel percentages in the main direction 9.2.1.1 (1) and (3) apply. Note: In addition to Note 2 of 9.2.1.1 (1), for slabs where the risk of brittle failure is small, $A _ { \mathsf { s } , \mathsf { m i n
- [4] EN1992-1-1_2004，页 158，条款 9.3.1.1, 9.3.1.2: (1) For the minimum and the maximum steel percentages in the main direction 9.2.1.1 (1) and (3) apply. Note: In addition to Note 2 of 9.2.1.1 (1), for slabs where the risk of brittle failure is small, $A _ { \mathsf { s } , \mathsf { m i n
- [5] EN1992-1-1 2004，页 62，条款 5.6.3: (1) The simplified procedure for continuous beams and continuous one way spanning slabs is based on the rotation capacity of beam/slab zones over a length of approximately 1,2 times the depth of section. It is assumed that these zones
- [6] EN1992-1-1 2004，页 158，条款 9.3: (1) This section applies to one-way and two-way solid slabs for which $b$ and $I _ { \mathsf { e f f } }$ are not less than $5 h$ (see 5.3.1).
- [7] DG_EN1992-1-1__-1-2，页 232，条款 : The data for two-way spanning slabs are applicable only to slabs supported on all four edges. If this is not met, the slab should be treated as one-way spanning. The thickness of the slab for continuous slabs is the same as for simply
- [8] DG_EN1992-1-1__-1-2，页 223，条款 : Guidance is provided in EN 1992-1-1 for estimating the transmission lengths in pretensioned members. A distinction is drawn between the transmission length over which the prestressing force is fully transmitted to the concrete $l _ {

## 28. 构件在哪些情况下无需设计抗剪力钢筋

- Excel 行号: 29
- 层级: Level 5 / 易错点与边界条件测试层

### 答案

根据欧洲规范 EN 1992-1-1 的规定，构件“无需设计抗剪钢筋”可分为**无需计算抗剪钢筋**和**可完全省略最小抗剪钢筋**两个层面。具体适用情况如下：

### 一、 无需计算抗剪钢筋的情况
1. **一般构件区域**：在构件的某些区域，如果由外部荷载和预应力产生的设计剪力 $V_{Ed}$ 小于或等于无抗剪钢筋构件的设计抗剪承载力 $V_{Rd,c}$，则该区域无需计算抗剪钢筋 [Ref-1] [Ref-4] [Ref-5]。
2. **T型截面翼缘与腹板交界处**腹板交界处**：对于翼缘与腹板交界处的纵向剪力，如果设计纵向剪应力 $V_{Ed}$ 小于或等于 $k f_{ctd}$，则不需要提供除抗弯钢筋之外的额外抗剪钢筋 [Ref-4]。

### 二、 可完全省略最小抗剪钢筋的情况
原则上，当计算表明不需要抗剪钢筋时，仍应根据规范第 9.2.2 节配置最小抗剪钢筋 [Ref-1] [Ref-4] [Ref-5]。但在以下特定情况下，**可完全省略最小抗剪钢筋** [Ref-1] [Ref-4] [Ref-5]：
1. **具备荷载横向重分布能力的板类构件**：如实心板、肋形板或空心板。
2. **次要构件**：对结构整体抗力和稳定性没有显著贡献的构件（例如跨度 $\le 2\text{ m}$ 的过梁）。

### 三、 特殊材料与验算场景的补充规定
1. **轻骨料混凝土构件**：对于轻骨料混凝土，无需设计抗剪钢筋时的抗剪承载力 $V_{lRd,c}$ 需采用专门的公式（Expression 11.6.2）进行计算，其计算逻辑与普通混凝土类似，但参数取值不同 [Ref-9] [Ref-16]。
2. **疲劳验算**：对于在承载能力极限状态（ULS）下无需设计抗剪钢筋的构件，在进行疲劳验算时，若频繁荷载组合下的最大和最小设计剪力（$V_{Ed,max}$ 和 $V_{Ed,min}$）满足规范 6.8.7 节的限制条件，可假定混凝土自身足以抵抗剪切引起的疲劳效应，无需额外配置抗剪钢筋 [Ref-6]。

### 四、 国家附录（National Annex）及前提提醒
在实际工程计算中，以下关键参数的取值必须核查项目所在国的**国家附录（National Annex）**，不得直接默认使用推荐值：
- 计算普通混凝土 $V_{Rd,c}$ 时的参数 $C_{Rd,c}$、$v_{min}$ 和 $k_1$ [Ref-4]。
- 计算轻骨料混凝土 $V_{lRd,c}$ 时的参数 $C_{lRd,c}$、$v_{l,min}$ 和 $k_1$ [Ref-9]。
- T型截面翼缘纵向剪力判定条件 $V_{Ed} \le k f_{ctd}$ 中的参数 $k$（规范推荐值为 $0.4$） [Ref-4]。

---
**依据位置：**
- [Ref-1] EN 1992-1-1:2004, 6.2.1 (3), (4), 页码 84-85
- [Ref-4] EN 1992-1-1:2004, 6.2.1 (3), (4) 及 6.2.2, 6.2.4 (6), 页码 84-92
- [Ref-5] EN 1992-1-1:2004, 6.2.1 (3), (4), 页码 84-85
- [Ref-6] EN 1992-1-1:2004, 6.8.7 (4), 页码 116-117
- [Ref-9] EN 1992-1-1:2004, 11.6.1 (1), 页码 189-190
- [Ref-16] EN 1992-1-1:2004, 11.6.1 (Expression 11.6.2), 页码 189-190

### 来源

- [1] EN1992-1-1_2004，页 84，条款 6.2.1, (1)P: (1)P For the verification of the shear resistance the following symbols are defined: $V _ { \sf R d , c }$ is the design shear resistance of the member without shear reinforcement. $V _ { \sf R d , s }$ is the design value of the shear
- [2] EN1992-1-1 2004，页 84，条款 : $$ V _ { \mathrm { R d } } = V _ { \mathrm { R d , s } } + V _ { \mathrm { c c d } } + V _ { \mathrm { t d } } $$
- [3] EN1992-1-1_2004，页 88，条款 : $$ V _ { \mathrm { R d , \thinspace s } } = \frac { A _ { \mathrm { s w } } } { s } z f _ { \mathrm { y w d } } \thinspace { \sf c o t } \theta\tag{6.8} $$
- [4] EN1992-1-1_2004，页 84，条款 6.2.1, (1)P: (1)P For the verification of the shear resistance the following symbols are defined: $V _ { \sf R d , c }$ is the design shear resistance of the member without shear reinforcement. $V _ { \sf R d , s }$ is the design value of the shear
- [5] EN1992-1-1 2004，页 84，条款 6.2.1, (1)P: (1)P For the verification of the shear resistance the following symbols are defined: $V _ { \sf R d , c }$ is the design shear resistance of the member without shear reinforcement. $V _ { \sf R d , s }$ is the design value of the shear
- [6] EN1992-1-1_2004，页 116，条款 6.8.7: (3) Expression (6.77) also applies to the compression struts of members subjected to shear. In this case the concrete strength $\pmb { f } _ { \mathrm { c d , f a t } }$ should be reduced by the strength reduction factor (see 6.2.2 (6)).
- [7] EN1992-1-1 2004，页 159，条款 9.3.2: (1) A slab in which shear reinforcement is provided should have a depth of at least $2 0 0 ~ \mathsf { m m }$ . (2) In detailing the shear reinforcement, the minimum value and definition of reinforcement ratio in 9.2.2 apply, unless
- [8] DG_EN1992-1-1__-1-2，页 97，条款 : This area is probably of limited importance for beams where some shear reinforcement will always be provided but is of major importance for slabs where it is often very inconvenient to provide shear reinforcement. It is of particular

## 29. 需要设计剪力筋的构件有什么特征

- Excel 行号: 30
- 层级: Level 4 / 复杂场景与多参数耦合层

### 答案

根据欧洲规范 EN 1992-1-1 的规定，需要设计（配置）剪力筋的构件主要根据其**受力状态**和**构件类型**表现出以下特征。具体可分为“必须通过计算配置”、“仅需构造配置”以及“冲切特殊配置”三种情况：

### 1. 必须通过计算配置剪力筋的构件（计算控制）
* **力学特征**：在构件的特定区域内，由外部荷载和预应力（粘结或非粘结）产生的剪力设计值 $V_{Ed}$ **大于** 无剪力筋构件的混凝土抗剪承载力设计值 $V_{Rd,c}$（即满足 $V_{Ed} > V_{Rd,c}$）[Ref-1, Ref-10, Ref-15]。
* **设计要求**：必须提供足够的计算剪力筋，使得筋，使得该区域的抗剪承载力满足 $V_{Ed} \le V_{Rd}$ [Ref-1, Ref-10, Ref-15]。同时，构件任何部位的总剪力（扣除翼缘贡献后）不得超过由混凝土受压腹杆压碎控制的极限抗剪承载力上限 $V_{Rd,max}$ [Ref-15]。

### 2. 仅需配置最小剪力筋的构件（构造控制）
* **力学特征**：在 $V_{Ed} \le V_{Rd,c}$ 的区域，理论上混凝土自身已足以抵抗剪力，不需要通过计算配置剪力筋 [Ref-1, Ref-10, Ref-15]。
* **设计要求**：除下文提到的“豁免构件”外，此类构件（如常规的混凝土梁）**仍必须按照构造要求配置最小剪力筋** [Ref-1, Ref-10, Ref-15]。最小剪力筋需满足规范第 9.2.2 节的构造规定，例如：箍筋与构件纵轴的夹角应在 $45^\circ$ 到 $90^\circ$ 之间，且至少有一定比例（推荐值为 50%）必须为包裹纵向受拉钢筋和受压区的封闭式箍筋 [Ref-17]。

### 3. 受冲切作用的板类构件（冲切控制）
* **力学特征**：对于平板（Flat slabs）或基础等承受集中荷载或柱反力的构件，当控制周长上的冲切剪力设计值超过混凝土的抗冲切承载力时 [Ref-13, Ref-20]。
* **设计要求**：需要配置冲切剪力筋（如抗冲切箍筋或弯起钢筋）。冲切剪力筋应布置在加载区域（或柱面）与不需要剪力筋的外侧控制周长之间，至少布置两圈，且第一圈剪力筋距离加载面或柱面的距离不得超过 $d/2$（$d$ 为有效高度）[Ref-13, Ref-20]。

---

### 💡 补充：可豁免配置剪力筋的构件特征（无需设计）
规范明确指出，即使在计算不需要剪力筋（$V_{Ed} \le V_{Rd,c}$）的情况下，以下两类构件也可以**完全省略**最小剪力筋 [Ref-1, Ref-10, Ref-15]：
1. **能够进行横向荷载重分布的板类构件**：如实心板、肋形板或空心板。
2. **次要构件**：对结构整体抗力和稳定性没有显著贡献的构件（例如跨度 $\le 2\text{ m}$ 的过梁）。

### ⚠️ 工程师注意事项（国家附录限制）
* **参数取值**：计算 $V_{Rd,c}$ 时的关键参数（如 $C_{Rd,c}$、$v_{min}$、$k_1$）以及最小剪力筋配筋率下限 $\rho_{w,min}$ 的具体数值，需查阅项目所在国的**国家附录（National Annex）**，规范仅提供了推荐值 [Ref-1, Ref-17]。
* ** strut 角度限制**：在计算配置剪力筋时，混凝土受压腹杆倾角 $\theta$ 的余切值 $\cot\theta$ 受到限制（规范推荐限制为 $1 \le \cot\theta \le 2.5$），具体限值同样需以国家附录为准 [Ref-2, Ref-11, Ref-16]。

### 来源

- [1] EN1992-1-1_2004，页 84，条款 6.2.1, (1)P: (1)P For the verification of the shear resistance the following symbols are defined: $V _ { \sf R d , c }$ is the design shear resistance of the member without shear reinforcement. $V _ { \sf R d , s }$ is the design value of the shear
- [2] EN1992-1-1_2004，页 88，条款 : $$ 1 \leq \cot \theta \leq 2 , 5\tag{6.7N} $$
- [3] EN1992-1-1_2004，页 85，条款 : $$ V _ { \mathrm { R d , c } } = [ C _ { \mathrm { R d , c } } k ( 1 0 0 \ \rho _ { \mathrm { 1 } } \ f _ { \mathrm { c k } } ) ^ { 1 / 3 } + k _ { \mathrm { 1 } } \ \sigma _ { \mathrm { c p } } ] \ b _ { \mathrm { w } } d\tag{6.2.a} $$
- [4] EN1992-1-1_2004，页 85，条款 : $$ k = 1 + \sqrt { \frac { 2 0 0 } { d } } \leq 2 , 0 \mathrm { ~ w i t h ~ } d \mathrm { ~ i n ~ m m } $$
- [5] EN1992-1-1_2004，页 85，条款 : $$ V _ { \mathrm { R d , c } } = \left( V _ { \mathrm { m i n } } + k _ { 1 } \sigma _ { \mathrm { c p } } \right) b _ { \mathrm { w } } d\tag{6.2.b} $$
- [6] EN1992-1-1_2004，页 88，条款 : $$ V _ { \mathrm { R d , \mathscr { m } a x } } = \alpha _ { \mathrm { c w } } b _ { \mathrm { w } } z \ \nu _ { 1 } \ f _ { \mathrm { c d } } / ( \mathsf { c o t } \theta + \mathsf { t a n } \theta )\tag{6.9} $$
- [7] EN1992-1-1_2004，页 91，条款 : $$ V _ { \mathsf { E d } } = ~ \Delta F _ { \mathsf { d } } / ( h _ { \mathsf { f } } \cdot \Delta x )\tag{6.20} $$
- [8] EN1992-1-1_2004，页 88，条款 : $$ \nu _ { 1 } ~ = 0 , 6 ~ \mathrm { f o r } ~ f _ { \mathrm { c k } } \leq 6 0 ~ \mathsf { M P a } $$

## 30. 结构抗扭转设计程序是怎样的

- Excel 行号: 31
- 层级: Level 2 / 构件极限状态计算层

### 答案

根据欧洲规范 EN 1992-1-1 及其配套设计指南，混凝土结构抗扭转设计的程序可系统地划分为扭转类型识别、截面建模、承载力验算与配筋计算等步骤。以下是可供工程师直接使用的设计程序说明：

### 一、 扭转类型识别与设计前提
在开始计算前，必须首先识别扭转的性质，以决定设计的深度：
1. **平衡扭转（Equilibrium torsion）**：当结构的静力平衡直接依赖于构件的抗扭承载力时（例如悬挑雨篷的边缘梁），必须进行涵盖承载能力极限状态（ULS）和正常使用极限状态（SLS）的完整抗扭设计 [Ref-5], [Ref-6], [Ref-9]。
2. **协调扭转（Compatibility torsion）**：在超静定结构中，若扭转仅由变形协调引起，且结构稳定性不依赖抗扭承载力（例如单侧有梁板框架的边缘梁），通常在 ULS 下无需进行抗扭承载力计算。但必须配置规范规定的最小抗扭钢筋（箍筋和纵筋）以防止过度开裂 [Ref-5], [Ref-6], [Ref-9]。

### 二、 截面建模与扭矩分配
1. **等效薄壁截面**：截面抗扭承载力基于薄壁闭合截面计算（通过闭合剪流满足平衡），实心截面可等效为薄壁截面 [Ref-5], [Ref-6]。
2. **复杂截面划分**：复杂形状（如 T 形截面）可划分为一系列子截面，每个子截面等效为薄壁截面，总抗扭承载力为各子截面承载力之和 [Ref-5], [Ref-6]。
3. **扭矩分配**：作用扭矩在各子截面上的分配应与其未开裂抗扭刚度成正比 [Ref-5], [Ref-6]。
4. **翘曲扭转**：对于闭合薄壁和实心截面，通常可忽略翘曲扭转；对于开口薄壁构件，可能需要考虑翘曲扭转，并按弯曲、轴向力和剪切的设计规则进行计算 [Ref-13]。

### 三、 抗扭设计计算步骤（ULS）

#### 步骤 1：确定等效截面几何参数
- **等效壁厚 $t_{ef,i}$**：取 $A/u$（$A$ 为外轮廓总面积，$u$ 为外轮廓周长），但不应小于纵向钢筋中心到边缘距离的两倍；对于空心截面，等效壁厚不应大于实际壁厚 [Ref-5]。
- **$A_k$**：连接墙中心线包围的面积（包括内部空心部分） [Ref-5]。
- **$u_k$**：面积 $A_k$ 的周长 [Ref-5]。

#### 步骤 2：验算截面尺寸限制（混凝土压杆承载力）
- 受扭和受剪构件的最大承载力受混凝土压杆抗压能力限制 [Ref-1]。
- 需满足规范规定的剪扭组合截面限制条件，确保设计效应不超过包含 $T_{Rd,max}$（设计抗扭承载力）和 $V_{Rd,max}$（最大设计抗剪承载力）的组合上限 [Ref-1]。
- 选择混凝土压杆倾角 $\theta$（$\cot\theta$ 通常限制在 1.0 到 2.5 之间），使得设计扭矩 $T_{Ed}$ 不超过最大抗扭承载力 $T_{Rd,max}$ [Ref-7], [Ref-8]。

#### 步骤 3：计算抗扭横向钢筋（箍筋）
- 所需抗扭横向钢筋面积按指南公式计算：$A_{sw}/s = T_{Ed} / (2 A_k f_{yw,d} \cot\theta)$，其中 $f_{yw,d}$ 为横向钢筋设计屈服强度 [Ref-7], [Ref-8]。
- **剪扭叠加**：当剪力和扭矩共同作用时，抗剪箍筋和抗扭箍筋可叠加，且必须假设相同的压杆倾角 $\theta$ [Ref-5]。

#### 步骤 4：计算抗扭纵向钢筋
- 纵筋总面积 $\sum A_{sl}$ 根据规范公式 (6.28) 计算：
  $$ \frac{\sum A_{sl} f_{yd}}{u_k} = \frac{T_{Ed}}{2 A_k} \cot\theta $$
  其中 $f_{yd}$ 为纵筋设计屈服强度 [Ref-2], [Ref-5]。
- **布置与叠加原则**：纵筋通常应沿截面边长 $z_i$ 均匀分布（较小截面可集中在两端） [Ref-1]。在受压弦杆中，纵筋可按可用压力比例减少；在受拉弦杆中，抗扭纵筋应与其他受力纵筋叠加 [Ref-1]。

### 四、 豁免条件（仅需最小配筋的情况）
对于近似矩形的实心截面，如果满足 $T_{Ed} \le T_{Rd,c}$（扭转开裂扭矩，可通过设定剪应力 $\tau_{t,i} = f_{ctd}$ 确定），且剪力也满足相应的免算条件，则无需进行抗扭承载力计算，仅需按规范配置最小抗扭钢筋 [Ref-1]。

### 五、 依据位置
- **位置
- **规范 EN 1992-1-1:2004**：
  - 扭转类型与一般规定：条款 6.3.1(1)P ~ (5) [Ref-5], [Ref-6], [Ref-12]
  - 设计程序与配筋计算：条款 6.3.2(1) ~ (5) 及公式 (6.26) ~ (6.28) [Ref-1], [Ref-2], [Ref-3], [Ref-4], [Ref-5]
  - 翘曲扭转：条款 6.3.3 [Ref-13]
- **设计指南 DG_EN1992-1-1**：
  - 扭转概念与验证步骤总结：章节 6.4.1, 6.4.3 [Ref-7], [Ref-8], [Ref-9]

*注：在实际工程中，若存在轴向应力（如预应力构件），计算最大抗扭承载力 $T_{Rd,max}$ 时需按规范引入轴向应力影响系数 $\alpha_{cw}$ 进行修正 [Ref-7], [Ref-8]。*

### 来源

- [1] EN1992-1-1_2004，页 95，条款 6.3.2: In compressive chords, the longitudinal reinforcement may be reduced in proportion to the available compressive force. In tensile chords the longitudinal reinforcement for torsion should be added to the other reinforcement. The
- [2] EN1992-1-1_2004，页 95，条款 : $$ \frac { \sum A _ { \mathrm { s l } } \mathsf { f } _ { \mathrm { y d } } } { u _ { \mathrm { k } } } = \frac { T _ { \mathrm { E d } } } { 2 A _ { \mathrm { k } } } \mathsf { c o t } \theta\tag{6.28} $$
- [3] EN1992-1-1_2004，页 95，条款 : $$ \tau _ { \mathrm { t , i } } t _ { \mathrm { e f , i } } = \frac { T _ { \mathrm { E d } } } { 2 A _ { \mathrm { k } } }\tag{6.26} $$
- [4] EN1992-1-1_2004，页 95，条款 : $$ V _ { \sf E d , i } = \tau _ { { \sf t } , { \sf i } } t _ { { \sf e f } , { \sf i } } z _ { \sf i }\tag{6.27} $$
- [5] EN1992-1-1_2004，页 94，条款 6.3.1, (1)P: (1)P Where the static equilibrium of a structure depends on the torsional resistance of elements of the structure, a full torsional design covering both ultimate and serviceability limit states shall be made. (2) Where, in statically
- [6] EN1992-1-1_2004，页 94，条款 6.3.1, (1)P: (1)P Where the static equilibrium of a structure depends on the torsional resistance of elements of the structure, a full torsional design covering both ultimate and serviceability limit states shall be made. (2) Where, in statically
- [7] DG_EN1992-1-1__-1-2，页 107，条款 : In normal building structures, torsion generally arises as a secondary effect, and specific calculations are not necessary. Torsional cracking is generally adequately controlled by reinforcement provided to resist shear. Even when torsion
- [8] DG_EN1992-1-1__-1-2，页 108，条款 : In EN 1992-1-1, the torsional resistance is calculated on the basis of a thin-walled closed cross-section. Solid sections are replaced by equivalent thin-walled sections. The wall thickness is taken as A/u, where A is the total area of

## 31. 单向板或双向板连续板在计算跨高比限值时K值取多少？

- Excel 行号: 32
- 层级: Level 5 / 易错点与边界条件测试层

### 答案

### 直接结论
在计算单向板或双向连续板的跨高比限值时，结构体系系数 $K$ 的推荐取值根据跨度位置（端跨或中间跨）有所不同：
- **端跨**（End span）：$K = 1.3$
- **中间跨**（Interior span）：$K = 1.5$

### 依据与说明
1. **端跨与中间跨的区分**：
   - 连续单向板，或仅在一个长边方向连续的双向板，其**端跨**的 $K$ 值取 1.3 [Ref-1]。
   - 单向或双向连续板的**中间跨**，其 $K$ 值取 1.5 [Ref-1]。

2. **双向板的跨度取值要求**：
   - 对于双向板，跨高比验算必须基于**较短的跨度**（shorter span）进行计算 [Ref-1]。

3. **国家附录（National Annex）优先原则**：
   - 上述 $K$ 值为欧洲规范（EN 1992-1-1）给出的推荐值。各成员国可在其国家附录中对 $K$ 值进行修改，实际工程中必须查阅并采用项目所在国的国家附录规定值 [Ref-4]。

4. **轻骨料混凝土（LWAC）修正**：
   - 若连续板采用轻骨料混凝土，按上述 $K$ 值计算得出的基本跨高比限值还需额外乘以折减系数 $\eta_E^{0.15}$ [Ref-8]。

### 依据位置
- [Ref-1] EN1992-1-1_2004, 7.4.2, Table 7.4N 及 Note 2 (页码: 127-129)
- [Ref-4] EN1992-1-1 2004, 7.4.2 (页码: 127-129)
- [Ref-8] EN1992-1-1 2004, 11.7 (页码: 191)1)

### 来源

- [1] EN1992-1-1_2004，页 127，条款 Table 7: Table 7.4N: Basic ratios of span/effective depth for reinforced concrete members without axial compression <table><tr><td> Structural System</td><td>K</td><td>Concrete highly stressed $\rho = 1 { , } 5 \%$ </td><td>Concrete lightly
- [2] EN1992-1-1_2004，页 127，条款 7.4.2, (1)P: (1)P Generally, it is not necessary to calculate the deflections explicitly as simple rules, for example limits to span/depth ratio may be formulated, which will be adequate for avoiding deflection problems in normal circumstances. More
- [3] EN1992-1-1_2004，页 126，条款 7.4.1, (1)P: (1)P The deformation of a member or structure shall not be such that it adversely affects its proper functioning or appearance. (2) Appropriate limiting values of deflection taking into account the nature of the structure, of the finishes,
- [4] EN1992-1-1 2004，页 127，条款 7.4.2, (1)P: (1)P Generally, it is not necessary to calculate the deflections explicitly as simple rules, for example limits to span/depth ratio may be formulated, which will be adequate for avoiding deflection problems in normal circumstances. More
- [5] DG_EN1992-1-1__-1-2，页 183，条款 : As has been seen, the calculation of deflections is a tedious operation and the results will be of limited reliability. Most codes therefore do not require explicit calculations to be carried out to check deflections except in special
- [6] DG_EN1992-1-1__-1-2，页 183，条款 : The result of this exercise can be presented in the form of the set of curves shown in Figure 8.17 combined with the values of k given in Table 7.4N in Eurocode 2. Figure 8.17 is drawn for k ¼ 1 and therefore, to obtain the appropriate
- [7] DG_EN1992-1-1__-1-2，页 183，条款 : Thus, for an elastic material, limiting the span/depth ratio will limit the ratio of the deflection to the span. This is an entirely rigorous way of controlling the deflection in these circumstances provided that the limits to deflection
- [8] EN1992-1-1 2004，页 191，条款 11.7, (1)P: (1)P The basic ratios of span/effective depth for reinforced concrete members without axial compression, given in 7.4.2, should be reduced by a factor $\eta _ { \mathsf { E } } ^ { 0 , 1 5 }$ when applied to LWAC.

## 32. 500x500的中间跨框架柱的冲切周长是多少？

- Excel 行号: 33
- 层级: Level 5 / 易错点与边界条件测试层

### 答案

根据欧洲规范 EN 1992-1-1，冲切验算涉及两个关键的“冲切周长”概念：**柱周边周长（$u_0$）**和**基本控制周长（$u_1$）**。对于 500×500 mm 的中间跨框架柱（内部柱），具体取值与计算规则如下：

### 1. 柱周边周长 ($u_0$)
* **明确数值**：**2000 mm**。
* **依据与说明**：$u_0$ 主要用于验算柱周边的最大冲切剪应力（防止混凝土局部压碎）。规范明确规定，对于内部柱（interior column），$u_0$ 等于柱截面的周长 [Ref-2]。因此，$u_0 = 4 \times 500 = 2000 \text{ mm}$。

### 2. 基本控制周长 ($u_1$)
* **确定规则**：位于距离柱边缘 **$2.0d$** 处 [Ref-5]。
5]。
* **依据与说明**：$u_1$ 主要用于验算混凝土自身的抗冲切承载力以及判断是否需要配置抗冲切钢筋。规范规定基本控制周长通常取在距离加载区域（柱边缘）$2.0d$ 的位置，并应以使周长长度最小化的方式构建 [Ref-5]。对于矩形内部柱，其几何形状为柱截面外扩 $2d$ 形成的带圆角矩形（由4条直线段和4个半径为 $2d$ 的四分之一圆弧组成）。
* **证据局限说明**：根据当前检索结果，规范正文中未直接提供 $u_1$ 的代数展开计算公式（如 $2(c_1+c_2) + 2\pi \cdot 2d$），实际工程中需根据上述几何定义进行计算，或参考具体国家附录及设计指南。

### 3. 适用条件与限制提醒
在实际应用上述周长时，请务必核对以下项目条件：
* **有效高度 $d$ 的取值**：计算 $u_1$ 时，$d$ 应取板在两个正交方向（y向和z向）上有效高度的平均值，即 $d = (d_y + d_z) / 2$ [Ref-4]。
* **洞口折减影响**：如果柱附近存在楼板洞口，且柱边缘到洞口边缘的最短距离不超过 $6d$，则基本控制周长 $u_1$ 中位于“从加载区域中心向洞口轮廓所作两条切线之间”的部分应被视为无效，必须从总周长中扣除 [Ref-5]。
* **柱位置前提**：上述 $u_0$ 取柱全周长的规则仅适用于**内部柱**。若该柱实际为边柱或角柱，$u_0$ 和 $u_1$ 的计算规则及有效周长将发生改变 [Ref-2], [Ref-5]。

### 依据位置
* $u_0$ 内部柱定义：EN 1992-1-1 2004, 条款 6.4.5(3) [Ref-2]
* $u_1$ 距离与构建原则：EN 1992-1-1 2004, 条款 6.4.2(1) [Ref-5]
* 洞口导致周长无效的规则：EN 1992-1-1 2004, 条款 6.4.2(3) [Ref-5]
* 平均有效高度 $d$ 的定义：EN 1992-1-1 2004, 条款 6.4.3(3) [Ref-4]

### 来源

- [1] DG_EN1992-1-1__-1-2，页 110，条款 : Having chosen a basic form for the perimeter, it is next necessary to consider the distance from the loaded area at which it should be located. Since the treatment of shear is empirical, there is no absolutely defined answer to this
- [2] EN1992-1-1 2004，页 104，条款 6.4.4: (1) The punching shear resistance of a slab should be assessed for the basic control section according to 6.4.2. The design punching shear resistance [MPa] may be calculated as follows: where: $\pmb { f } _ { \mathtt { C } \mathtt { K } }$
- [3] DG_EN1992-1-1__-1-2，页 110，条款 : Punching shear is a local shear failure around a concentrated load on a slab. The most common situations where punching shear has to be considered is the region immediately surrounding a column in a flat slab or where a column is supported
- [4] EN1992-1-1 2004，页 101，条款 6.4.3, (1)P: (1)P The design procedure for punching shear is based on checks at the face of the column and at the basic control perimeter $u _ { 1 }$ . If shear reinforcement is required a further perimeter uout,ef (see figure 6.22) should be found
- [5] EN1992-1-1_2004，页 97，条款 6.4.1, (1)P: (1)P The rules in this Section complement those given in 6.2 and cover punching shear in solid slabs, waffle slabs with solid areas over columns, and foundations. (2)P Punching shear can result from a concentrated load or reaction acting
- [6] EN1992-1-1 2004，页 97，条款 6.4.1, (1)P: (1)P The rules in this Section complement those given in 6.2 and cover punching shear in solid slabs, waffle slabs with solid areas over columns, and foundations. (2)P Punching shear can result from a concentrated load or reaction acting
- [7] EN1992-1-1_2004，页 97，条款 6.4.1, (1)P: (1)P The rules in this Section complement those given in 6.2 and cover punching shear in solid slabs, waffle slabs with solid areas over columns, and foundations. (2)P Punching shear can result from a concentrated load or reaction acting
- [8] EN1992-1-1_2004，页 101，条款 6.4.3, (1)P: (1)P The design procedure for punching shear is based on checks at the face of the column and at the basic control perimeter $u _ { 1 }$ . If shear reinforcement is required a further perimeter $u _ { \mathrm { o u t , } }$ ef (see figure
