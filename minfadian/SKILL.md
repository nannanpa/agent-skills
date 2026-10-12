---
name: minfadian
displayName: 民法典速查
version: "1.0.0"
agent_created: true
description: "《中华人民共和国民法典》法条速查技能：1260条全文按7编84章及附则共85个分册存储（条文为原文），支持按编/章/条精确定位、生活工作场景检索。写材料引用法条、审查合同条款、咨询婚姻继承侵权借贷等问题时使用。触发词：民法典、法条、第X条、诉讼时效、合同效力。"
---

# 中华人民共和国民法典 · 法条速查

**通过**：2020年5月28日十三届全国人大三次会议 | **施行**：2021年1月1日 | **规模**：7编84章1260条
**同时废止**（第1260条）：民法通则、民法总则、婚姻法、继承法、收养法、担保法、合同法、物权法、侵权责任法

## 使用方法

- **问具体条文**（"诉讼时效是哪条""第586条说什么"）→ 直接 grep 章文件给原文
- **问生活/工作场景**（"学校租的房子漏水谁负责"）→ 先查 [cheatsheet.md](cheatsheet.md) 场景定位表，再读对应章
- **问法律术语**（"善意取得""居住权"）→ 查 [glossary.md](glossary.md)
- **要判断规则**（"定金最多收多少""保证没约定算哪种"）→ 查 [patterns.md](patterns.md)
- 条文引用一律给**条号＋原文**，再附一句白话

## 核心规则速览（最常查的判断标准）

- **民事行为能力**：18周岁为完全（第17/18条）；8周岁以上有限（第19条），8周岁以下无（第20条）；16—18周岁以自己劳动收入为主要生活来源的视为完全（第18条第2款）
- **诉讼时效**：一般3年（第188条），自知道权利受损及义务人之日起算；最长保护20年（第188条第2款）；中止（第194条）、中断（第195条）
- **定金**：不得超过主合同标的额20%，超过部分无定金效力（第586条）；定金罚则双倍返还/不予返还（第587条）
- **违约金**：约定过高可请求法院适当减少、过低可请求增加（第585条）
- **保证方式**：没有约定或约定不明的，按**一般保证**承担（第686条第2款）——较原《担保法》的重大反转
- **借款利率**：禁止高利放贷（第680条）
- **离婚冷静期**：协议离婚需30日冷静期＋30日内双方亲自申领（第1077条）
- **居住权**：书面合同＋登记设立，不得转让继承（第367/368条）
- **自愿紧急救助**：造成受助人损害的不担责（第184条）；正当防卫（第181条）、紧急避险（第182条）、自甘风险（第1176条）、自助行为（第1177条）
- **高空抛物**：禁止；查不清时可能由可能加害的建筑物使用人补偿（第1254条）
- **职务代理**：执行法人工作任务的人员就其职权范围内事项以法人名义实施的民事法律行为，对法人发生效力（第170条）——盖章、签字审查常用
- **格式条款**：提供方对免除/减轻己方责任等条款负提示说明义务，未履行可主张不成为合同内容（第496条）

## 七编索引

**第一编 总则**（第1—204条）：
[基本规定](chapters/ch01.md) · [自然人](chapters/ch02.md) · [法人](chapters/ch03.md) · [非法人组织](chapters/ch04.md) · [民事权利](chapters/ch05.md) · [民事法律行为](chapters/ch06.md) · [代理](chapters/ch07.md) · [民事责任](chapters/ch08.md) · [诉讼时效](chapters/ch09.md) · [期间计算](chapters/ch10.md)

**第二编 物权**（第205—462条）：
[一般规定](chapters/ch11.md) · [物权的设立、变更、转让和消灭](chapters/ch12.md) · [物权的保护](chapters/ch13.md) · [一般规定](chapters/ch14.md) · [国家所有权和集体所有权、私人所有权](chapters/ch15.md) · [业主的建筑物区分所有权](chapters/ch16.md) · [相邻关系](chapters/ch17.md) · [共有](chapters/ch18.md) · [所有权取得的特别规定](chapters/ch19.md) · [一般规定](chapters/ch20.md) · [土地承包经营权](chapters/ch21.md) · [建设用地使用权](chapters/ch22.md) · [宅基地使用权](chapters/ch23.md) · [居住权](chapters/ch24.md) · [地役权](chapters/ch25.md) · [一般规定](chapters/ch26.md) · [抵押权](chapters/ch27.md) · [质权](chapters/ch28.md) · [留置权](chapters/ch29.md) · [占有](chapters/ch30.md)

**第三编 合同**（第463—988条）：
[一般规定](chapters/ch31.md) · [合同的订立](chapters/ch32.md) · [合同的效力](chapters/ch33.md) · [合同的履行](chapters/ch34.md) · [合同的保全](chapters/ch35.md) · [合同的变更和转让](chapters/ch36.md) · [合同的权利义务终止](chapters/ch37.md) · [违约责任](chapters/ch38.md) · [买卖合同](chapters/ch39.md) · [供用电、水、气、热力合同](chapters/ch40.md) · [赠与合同](chapters/ch41.md) · [借款合同](chapters/ch42.md) · [保证合同](chapters/ch43.md) · [租赁合同](chapters/ch44.md) · [融资租赁合同](chapters/ch45.md) · [保理合同](chapters/ch46.md) · [承揽合同](chapters/ch47.md) · [建设工程合同](chapters/ch48.md) · [运输合同](chapters/ch49.md) · [技术合同](chapters/ch50.md) · [保管合同](chapters/ch51.md) · [仓储合同](chapters/ch52.md) · [委托合同](chapters/ch53.md) · [物业服务合同](chapters/ch54.md) · [行纪合同](chapters/ch55.md) · [中介合同](chapters/ch56.md) · [合伙合同](chapters/ch57.md) · [无因管理](chapters/ch58.md) · [不当得利](chapters/ch59.md)

**第四编 人格权**（第989—1039条）：
[一般规定](chapters/ch60.md) · [生命权、身体权和健康权](chapters/ch61.md) · [姓名权和名称权](chapters/ch62.md) · [肖像权](chapters/ch63.md) · [名誉权和荣誉权](chapters/ch64.md) · [隐私权和个人信息保护](chapters/ch65.md)

**第五编 婚姻家庭**（第1040—1118条）：
[一般规定](chapters/ch66.md) · [结婚](chapters/ch67.md) · [家庭关系](chapters/ch68.md) · [离婚](chapters/ch69.md) · [收养](chapters/ch70.md)

**第六编 继承**（第1119—1163条）：
[一般规定](chapters/ch71.md) · [法定继承](chapters/ch72.md) · [遗嘱继承和遗赠](chapters/ch73.md) · [遗产的处理](chapters/ch74.md)

**第七编 侵权责任**（第1164—1260条）：
[一般规定](chapters/ch75.md) · [损害赔偿](chapters/ch76.md) · [责任主体的特殊规定](chapters/ch77.md) · [产品责任](chapters/ch78.md) · [机动车交通事故责任](chapters/ch79.md) · [医疗损害责任](chapters/ch80.md) · [环境污染和生态破坏责任](chapters/ch81.md) · [高度危险责任](chapters/ch82.md) · [饲养动物损害责任](chapters/ch83.md) · [建筑物和物件损害责任](chapters/ch84.md)

**附则**（第1259—1260条）：
[附则](chapters/ch85-faze.md)

## 高频场景 → 直达文件

| 场景 | 去处 |
|---|---|
| 合同签订/效力/盖章 | [ch32 订立](chapters/ch32.md)、[ch33 效力](chapters/ch33.md)＋总则编[ch06 民事法律行为](chapters/ch06.md) |
| 借贷/利率 | [ch42 借款合同](chapters/ch42.md)（第667—680条） |
| 担保/抵押/质押 | [ch43 保证](chapters/ch43.md)＋[ch27 抵押权](chapters/ch27.md)、[ch28 质权](chapters/ch28.md) |
| 买房/卖房 | [ch39 买卖合同](chapters/ch39.md)＋[ch22 建设用地使用权](chapters/ch22.md) |
| 租房/出租 | 租赁合同章＋买卖不破租赁（第725条） |
| 婚姻/离婚 | 婚姻家庭编各章（[ch69 离婚](chapters/ch69.md)含冷静期） |
| 继承/遗嘱 | 继承编各章＋遗产管理人（第1145条起） |
| 名誉/隐私/个人信息 | 人格权编（第990—1039条） |
| 校园/物业/高空坠物 | [ch84 建筑物和物件损害责任](chapters/ch84.md)、[ch17 相邻关系](chapters/ch17.md) |
| 诉讼时效 | [ch09](chapters/ch09.md)（第188—199条） |

## 支持文件

- [glossary.md](glossary.md) — 法律术语定义（指向条文）
- [patterns.md](patterns.md) — 高频适用规则与重大修法变化
- [cheatsheet.md](cheatsheet.md) — 场景决策速查表

## 范围与限度

- 本技能收录**2020年公布版民法典原文**；最高法配套司法解释（合同编通则解释、总则编解释、担保制度解释等）**未收录**——重大法律适用问题应结合现行司法解释
- 劳动关系（《劳动合同法》）、公司事务（《公司法》）、知识产权单行法、行政法**不在民法典范围内**，相关问题应提示适用专门法律
- 本技能供学习与材料参考，不构成正式法律意见
