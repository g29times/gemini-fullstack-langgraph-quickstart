> 本文由 [简悦 SimpRead](http://ksria.com/simpread/) 转码， 原文地址 [mp.weixin.qq.com](https://mp.weixin.qq.com/s/S8Ns6G7oqweq_GtTnar4HA)

![](https://mmbiz.qpic.cn/sz_mmbiz_gif/qpAK9iaV2O3sAVsSPfCN9UX44XiaoicbUJIrOGuaujdMNY6iaQewDZEX1GY3tcVk3QGeKJyUMMHBSMALvO8B7DZwsA/640?wx_fmt=gif&from=appmsg)

# 用好 Deep Research，能够大大地提升 AI 产品 GTM （go to market）的效率。

ChatGPT、Gemini、Perplexity...... 几乎所有主流的 AI 产品，都上线了 Deep Research。Deep Research 能够从制定计划到收集相关背景信息，最后生成高质量的研究成果，将以往耗时数小时的工作压缩到几分钟。

但如何用好 Deep Research，把它变成高水平的定制分析师，需要一些技巧，通过高质量的提示词和充足的背景信息「指导」，才能产出一份高质量的定制研究成果。

前 Meta 战略总监 Torsten Walbaum 写了一份使用 Deep Research 功能非常实用的指南，通过真实的 GTM 案例，从实用技巧、提示词公式、工具选择等角度进行了详细的阐述。

*   如何从 Deep Research 中获得最佳输出的实用技巧；
    
*   一个高效的 Deep Research 提示词怎么写，应该具备哪些要素；
    
*   ChatGPT、Gemini、Claude、Perplexity、Grok 等不同工具如何选择，适合哪些场景；
    
*   五个实用的 GTM 用例，包括可以直接使用的提示词模板；
    

原文链接：https://www.growthunhinged.com/p/deep-research-for-gtm

超 12000 人的「AI 产品市集」社群！不错过每一款有价值的 AI 应用。

邀请从业者、开发人员和创业者，飞书扫码加群： 

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3vjfgc8R5F1VLq8aaBdbicwZFjaqzADFlxgtbXCBgZDs3cbiaX2G0Uc2icQBbAjAUKhibk9icLcg6F9u8g/640?wx_fmt=png&from=appmsg&tp=webp&wxfrom=5&wx_lazy=1)

进群后，你有机会得到：  

*   最新、最值得关注的 AI 新品资讯；   
    
*   不定期赠送热门新品的邀请码、会员码；  
    
*   最精准的 AI 产品曝光渠道
    

**01** 
-------

**4 个技巧，**
----------

**从 Deep Research 中获得最佳结果**
---------------------------

无论你使用哪种 AI 工具（下文将详细介绍），有几个关键的局限性是你都应该了解的。

不过，别担心：所有这些局限性都有解决办法，我们将详细介绍能让你获得最佳结果的详细工作流程和提示技巧。

#### 技巧 1：**为** **AI** **指明高质量的信息来源**

你从 Deep Research 中获得的输出质量在很大程度上取决于 agent 所使用的信息来源。不幸的是，它们在这方面的判断往往不尽如人意：会把社交媒体上的观点当作事实，过分依赖个别来源，或者使用过时的数据。当报告完成后才发现这些问题，会让人非常沮丧，因为你将不得不重新做一遍，损失 15 分钟的时间以及宝贵的研究额度。

有两个简单的方法可以解决这个问题：

*   方法 1：在提示词中指定优先考虑哪种类型的来源（例如，优先考虑政府数据等一手来源，而非新闻文章等二手来源）
    
*   方法 2：使用像 GPT-5 或 Claude Opus 这样的 AI 模型创建一份特定的高质量来源清单，然后将其输入到 Deep Research 中（这部分，将在下面第四个小标题内容下的示例 5 中实际应用。)
    

此外，如果你希望获得更高的透明度，还可以要求研究 agent ：

1.  对任何提出的主张都提供文本引用；
    
2.  在报告中添加一个表格，列出所有来源，并说明每个来源的用途、类型、数据年份等；
    
3.  概述不同来源在数据方面存在的分歧，并分析可能的原因（如统计方法的差异）。
    
    ![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDsebqWAc5gnlBIgftYLQBiciaddsnhpMMmrEwk7qNTPTb7BQfElZGicicnAw/640?wx_fmt=png&from=appmsg)
    

ChatGPT 生成的来源概述表示例，此功能非默认提供

这个步骤只会给你的工作流程增加一分钟时间，但能为你省去很多后续的麻烦。

#### 技巧 2：**提供充足的背景信息来获得定制化洞察**

只需点击一下按钮就能获得对某个主题的深入概述，这已经相当不错了，但实用价值有限。要真正从中获得价值，你需要的是适合你特定情况的分析内容。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDsBeEOaMuIODORLH1L1gNH5FosEt3BAHTzg3XL0D9qRehIPgW8JfSnmw/640?wx_fmt=png&from=appmsg)

遗憾的是，大多数 Deep Research 工具并不习惯主动询问它们所需的背景信息。因此，如果你不主动提供相关信息，它们要么会做出假设，要么内容会很笼统。

为了避免这种情况，你你需要像对待一位人类同事一样，提供所有必要的背景信息。具体需要哪些信息取决于具体情况，但以下是一些你通常需要涉及的几点常见事项：

*   **你****所在的公司以及公司的运营方式**
    

*   如果你希望 AI 提出具体的行动建议和或关于如何实施这些建议的战术指导，这一点尤为重要。
    

*   如果你的公司知名度较高，通常只需提及你在哪家公司工作即可；但如果是一家初创公司，最好简要介绍公司的业务、规模，以及与具体任务相关的一切（例如 GTM 模式等）。
    

*   **你****确切想要实现的目标**
    

*   我发现，当人们使用 Deep Research 时，往往会给 AI 一个任务例如：「整理一份比较这些工具的报告」），但没有分享背后的原因和最终目标（例如：「我们试图更好地了解活动表现以进行规划和预算分配」）。
    

*   你对目标越透明清晰，对 AI 在其中的位置解释得越清楚，结果的影响就越大。如果请求是更大项目的一部分，确保分享到目前为止已完成的所有工作。
    

*   **[如适用]** **你****面临的限制条件**
    

*   如果存在会排除某些选项的硬性限制，请分享这些信息，以获得更有针对性的报告：
    
*   你有多少预算和人员来实施这个项目？
    
*   你是否有明确的截止日期？
    
*   根据过去的经验，哪些方案是管理层或法务部门不会批准的？
    

**专家****提示：**如果你不想每次提示 Deep Research 时都提供背景信息，可以创建一个项目。这样，你只需上传一次初始背景，每份研究报告都会增加你和 AI 之间的共同知识。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDsHCTmkibxiayA9WJxpib7Es3ChQC11qog6QxmCVBXoXyMs0eZLCDUu76RQ/640?wx_fmt=png&from=appmsg)

ChatGPT 中的项目示例

以上只是一个起点，但我发现要 brainstorm 出具体应该分享的内容，尤其是在试图快速推进时，其实挺困难的。

为了让事情变得更简单，我开始向 AI 寻求意见（GPT-5 和 Claude Opus 在这方面都做得很好）：

> 我计划生成一份关于 [X] 的 Deep Research 报告，目的是[Y]。为了获得一份定制化的、可操作的报告，我应该提供哪些背景信息？假设你没有任何先前对话的背景。

最后，如果你想确保自己没有遗漏任何内容，可以直接让 Deep Research  agent 向你索取更多背景信息：

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDslrGkRibEAOIYCcprMxrP0y3mnrpLKK2AsNr4t2rjEnrxZr4debwn3AQ/640?wx_fmt=png&from=appmsg)

#### 技巧 3：在开始之前要求一份研究计划

Gemini Deep Research 最大的优势在于它总是会在开始之前分享一个计划；这样，你可以在等待 20 分钟之前就做出调整，才发现其研究方法或报告重点与你的预期大相径庭。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDskxBicRgaia852K5GT6crIJqAESxdicEEZUr9pqf8LCUmDvfjvUy7Qwv1A/640?wx_fmt=png&from=appmsg)

其他工具都没有这样的功能；因此，你需要在提示词中明确要求研究计划：

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDsMKA3PIUVticyXCF7ltUC7SQenng4E3gtOdUPU6gazibA4h5qwNEztw3g/640?wx_fmt=png&from=appmsg)

注意：如果在提交初始提示词后，你回答了 AI 的任何追问，请务必重申这一要求，否则工具可能会「忘记」它。

在审查研究计划时，你可以从以下几个问题入手：

*   它涵盖了你感兴趣的所有内容吗？你是否需要任何额外的输出（例如，模板、代码片段等）？
    
*   你是否同意其方法和重点领域（例如， agent 计划如何评估不同的选项）？
    
*   AI 是否做出了任何假设，或者某些部分看起来是否笼统？如果是这样，你需要提供额外的背景信息。
    

#### 技巧 4：**指定清晰易读的报告格式**

AI 默认生成的报告往往难以阅读，尤其是当你想快速浏览获得最重要的见解时。

不过，通过合适的提示词很容易改变这种情况。你只需提出如下要求：

*   在文档开头和每个单独部分都加入摘要
    
*   先列出关键见解或建议，然后再详细说明
    
*   在适当的地方使用概述表格或视觉效果，而不是大段文字
    

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDs2fhibiatiaDUwvagzaB3vgdgx29AXuahLgyrCZD0ad5IVHr5rLiaBebgLQ/640?wx_fmt=png&from=appmsg)

**02**
------

**如何撰写高效的 Deep Research 提示词？**
------------------------------

综合以上所有技巧，并添加一些可选内容，这就是一份有效的 Deep Research 提示词模板。

只需复制此格式并填入你自己的信息（标有「#」的注释是为了解释每个部分，不应包含在提示词中）：

**上下滑动查看更多  
**

```
# Goal: State 1) what you’re ultimately trying to accomplish, and 2) what exactly you want the AI to do. Example:

<goal> We want to build an account score to inform account allocation to SDRs and prioritize which accounts we reach out to. The desired model will assign 1) a firmographic fit score (i.e. "Is this company generally a good fit?」) as well as 2) an intent score (i.e. "Is this account currently in the market / likely to buy?") to each account. </goal>




# Context: Include all relevant context for the request that’s not already in your Project. Example:

<context> We’re currently focused on the US market only. Our GTM and data stack consists of Salesforce, Marketo, Outreach, dbt and Snowflake; we’re open to buying intent data sources. Explainability of the model and scores is key </context>



# [Optional] Content: Specify what you want included in the final output, e.g. comparisons, SQL code snippets, specs for Salesforce custom objects etc.. Example:

<content> Please cover, at a minimum: 1) A detailed 「build vs. buy」 analysis and recommendation, 2) An overview of the various approaches for building this in-house, 3) How to operationalize the account score between Marketing and Sales, 4) How we can provide visibility for sales reps into how the scores were derived </content>

# [Optional] Style: Define the format of the report. This is best included in the Project custom instructions as it can usually be the same for each research task. Example:

<style> Follow the Pyramid Principle: State key takeaways or recommendations first, then add supporting arguments and data where appropriate. When you give a recommendation, make sure you explain exactly how you arrived at it. Use bullet points, overview tables and other formatting to make the report easy to parse. </style>

# [Optional] Sources: Specify which sources the AI should prioritize and/or how it should document them. Example:

<sources> For tool comparisons, focus on assessments from leading industry blogs or practitioners instead of claims from the companies themselves </sources>

# [Optional] Instructions: Provide misc. instructions (e.g. specific methodology or steps you want the AI to follow). Example:

<instructions> Please ask for any additional context you need before you proceed </instructions>

```

注意，大多数模块都标记为可选；你将在下面的示例中看到，我会根据每个研究任务的相关性，灵活选用不同模块。对于更简单的请求，无需过度设计。

**03** 
-------

**如何选择合适的 Deep Research 工具？**
-----------------------------

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDs2fhibiatiaDUwvagzaB3vgdgx29AXuahLgyrCZD0ad5IVHr5rLiaBebgLQ/640?wx_fmt=png&from=appmsg)

总体来看，ChatGPT 是最好的通用 Deep Research 工具，尤其是最近发布了 GPT-5（无需切换模型）以及具备 Agent Mode （代理模式，能与网站进行有效交互） 之后。

它有两个关键优势：

1.  与其他工具相比，它总是会主动询问背景信息
    
2.  它提供的报告是迄今为止最深入的，并且始终表现出良好的判断力
    

第一个优点是相对没那么重要的，因为你可以让其他工具做到同样的事情。然而，无论你如何优化提示，都无法让其他工具产生接近 ChatGPT 深度和严谨性的内容。

这意味着，如果你需要极其详细的信息或指导，ChatGPT 显然是首选。不过，如果你不需要一万字的深度剖析，其他工具也是不错的选择。例如：

*   **Gemini** 的表现通常几乎与 ChatGPT 一样好，并且使用限制更宽松，因此如果你的 ChatGPT 额度用完了，它是一个很好的备用选项
    
*   **Perplexity** 也是一个不错的选择，如果你希望将研究重点放在特定的网站或社交论坛上，因为它 1） 拥有更精细的来源控制，2） 在这方面更好地遵循指示。
    
*   **Claude、****Perplexity** 和 **Grok** 生成的报告简洁易读，字数在 1000-2000 字之间，非常适合作为深入研究某个主题的起点。
    

因此，在我们介绍下面的实际用例时，我会强调哪种工具最适合每种情况。

**04** 
-------

**Deep Research 在 GTM 中的 5 个实际用例**
----------------------------------

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDshJuGnl26xOM8CXZkqTm4EZwAA2LUTtYW3hkxx8VFIjlj9R181eEK7w/640?wx_fmt=png&from=appmsg)

#### 用例 1：**为大型内部项目创建分步指南**

*   最佳工具：ChatGPT Deep Research
    
*   亚军：Gemini Deep Research
    

> 「我们应该开始大规模地个性化我们的外联电子邮件。其他人都在这么做！」

任何在 GTM 工作的人都经历过这样的场景：有一天，当你愉快地在舒适区内工作时，一位高管突然交给你一项你毫无经验的任务，并要求你立即优先处理。

无论是新兴的 AI 应用，还是像潜在客户评分和归因分析这类基础性工作，没有哪家初创公司在每个领域都有专家。因此，迟早你会不得不处理一个自己完全不知道如何入手的大型项目。

Deep Research 是一个绝佳的资源，能让你在不到一小时的时间内快速上手。虽然你不会因此迅速成为认证专家，但你会了解到足够多的信息来为项目制定一个高级计划，并弄清楚哪些领域需要更深入地研究（或寻求帮助）。

让我们来看一个实际示例。假设你想构建（或重新构建）营销归因模型。你大致知道想要将归因用于什么，但不知道如何实施。

针对这个问题，一份有效的 Deep Research 提示词如下：

**上下滑动查看更多  
**

```
<goal> Please put together an in-depth, tactical guide on how to build out marketing attribution in-house for a startup. As a first step, we want a simple attribution model that considers touchpoints from the relevant programs (Email, LinkedIn etc.) and assigns a single source to each created opportunity. </goal>

<context> We’re a B2B SaaS startup selling meeting transcription software. We’re mostly targeting SMBs and are currently at $10M ARR, growing 100% YoY. We’re mostly marketing-led with most leads coming via LinkedIn Ads and programmatic email. We’re using Salesforce, Marketo, dbt, Snowflake. </context

<audience> Assume working knowledge with relevant tools and systems, but zero prior experience with marketing attribution </audience>

<structure> Provide an overview of the key decisions that need to be made and the major work streams. For each body of work, provide an overview of different relevant approaches we could choose from, and then provide a detailed step-by-step guide for your recommended one </structure>

<style> Follow the Pyramid Principle: State key takeaways or recommendations first, then add supporting arguments and data where appropriate. Use bullet points, overview tables and other formatting to make the report easy to parse. </style>

```

注意：这里的关键在于清晰地提供有关你公司流程和技术栈的信息，以便获得一份定制化的操作手册。

你将得到的结果是：一份端到端的归因指南，涵盖不同的方法、实施途径，以及实际操作的分步说明（包括 UTM 标记约定的建议、dbt 模型的模拟 SQL 代码等）：

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDsy6micbQBibrD00y0ECvU8aax7WWnJmAl6wrk8Dlqia3dR9bY0YtDwPOBg/640?wx_fmt=png&from=appmsg)

Full response  《如何使用 Deep Research 进行 GTM——由托尔斯滕 · 瓦尔鲍姆》：https://chatgpt.com/s/dr_68980556ae6081919cf1fc715a37e1f2

当然，这只是一个示例；你可以获得任何 GTM 主题的详细指南。以下是更多启发灵感的示例：

*   从零开始构建内容策略
    
*   从一个工具迁移到另一个工具（例如，从 HubSpot 迁移到 Marketo）
    
*   设计一套能最大程度减少市场与销售部门摩擦的 GTM 规划流程
    
*   为销售代表制定合适的薪酬方案
    

#### 用例 2：**深度研究竞争对手的广告策略**

*   最佳工具：GPT-5 agent 模式
    
*   亚军：Perplexity
    

在上面的示例中，目标是通过让 AI 审查大量不同来源并综合出最佳实践方法来全面理解一个主题。然而，有时你可能想相反的做法，对一个特定的数据源进行深入研究。

例如，你可能想弄清楚，当你在努力让广告投放的经济效益发挥作用时，你的竞争对手是如何通过 LinkedIn（或 Google）的付费广告取得成功增长的。

好消息是：你可以在广告库（LinkedIn/Google/Meta）中看到竞争对手投放的所有广告，包括私信广告。更好的消息是：你不需要手动花费几天时间筛选这些信息，只需让 AI 来完成繁重的工作即可。

ChatGPT、Claude 和 Grok 的标准研究模式不太适合这种情况，因为几乎不可能让它们在单个网站上进行详尽的搜索。Perplexity 的表现还不错，但真正的解决方案是在 ChatGPT 中开启 Agent Mode。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDs7lZC3hTDtGhNn8v4BC6E1WEMYojibB3WiaFO6ialVxL5YLroI2EClia3Pg/640?wx_fmt=png&from=appmsg)

Agent Mode 被宣传为研究和行动之间的桥梁，事实也确实如此。你可以告诉它打开广告库，查看 50-100 个广告，然后撰写一份详细的报告。如果提示得当，它本质上就是具有额外技能的 Deep Research ：它可以登录账户、点击开关和过滤器、截图等。

一份有效的提示词如下：

**上下滑动查看更多  
**

```
<goal> I'm trying to understand how [Company] uses LinkedIn ads to grow. Please leverage the LinkedIn Ads library (https://www.linkedin.com/ad-library/) to put together a comprehensive report on their positioning, messaging and tactics. </goal>

<context> The detail page for every ad will have a lot of relevant information to consider. For example, it shows what type of ad it is, from when to when it was active, how many impressions it got across regions etc. </context>

<content> Please cover at a minimum the following: 
- What ad formats (e.g. message ads vs. single image) and types (e.g. customer case studies, CEO thought leadership etc.) they're running 
- Which buyer personas they seem to be targeting 
- How they position themselves and core messages to their audiences 
- What their calls-to-action look like 
- What incentives they offer (e.g. money or gifts to take demos)  

Please make sure to include concrete examples for any claim you make (i.e. link to specific ads inline). Please link to at least 20 concrete ad examples (the URL will look like "https://www.linkedin.com/ad-library/detail/[ad_id]") </content>

<instructions> Please review 50+ ads and create a detailed report of 3,000 words or more summarizing your findings </instructions>

```

注意：如果希望获得的见解能贴合你的公司，请上传关于你公司的背景信息，或在上述提示词的 <背景> 部分进行扩展。

我使用这个提示词（以 AI 初创公司 ElevenLabs 为例），得到了如下结果：

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDsPuTNppHia9icbTVSIxeiaEKicB4RJaSr2090IAyR4keWQxEuH22LE2zodQ/640?wx_fmt=png&from=appmsg)

完整报告见：https://chatgpt.com/s/68966112f2c081919e74bc7e5b241f6c

可以说，这份报告相当不错。特别棒的是：除了链接到具体的广告示例外， agent 还截取了屏幕截图，这一功能为更多应用场景开辟了可能。

#### 用例 3：**对网站首页或着陆页进行全面审计**

*   最佳工具：ChatGPT agent 模式
    
*   亚军：Gemini Deep Research
    

如果想对你的网站主页进行全面改造，你需要：

1.  研究最佳实践（例如在《Growth Unhinged》中提到的内容）
    
2.  查看竞争对手的网站，了解他们的做法
    
3.  详细检查自己的网站，找出有改进空间的地方
    
4.  制作计划更改的原型并起草新文案
    

Deep Research 能大大加快这一进程，其提供的评估能帮你完成约 80% 的工作；你仍需要自己进行完善，但可以省去大部分繁重的工作。

这是一个对我很有效的提示词结构（以 Linear 的定价页面为例）：

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDs16TiaKIJibtXfZoGsjc6LKsvHXlic3XK2e2DUaPHdGsNIcZvW3AXJibwaw/640?wx_fmt=png&from=appmsg)

```
10 分钟后，我得到了一份约 7600 字的分析报告，其中充满了可操作的建议分析报告：https://chatgpt.com/share/6897ced1-bc00-8002-aa04-d399da22217注意：如果希望获得的见解能贴合你的公司，请上传关于你公司的背景信息，或在上述提示词的 <背景> 部分进行扩展。




```

```
<goal> Please put together an in-depth analysis of Linear's pricing page (http://linear.app/pricing), critiquing its effectiveness and highlighting where 1) it adheres to industry best practices, 2) it stands out via innovative ideas and 3) where it falls short. </goal>

<structure & content> After a general review of the page, please provide detailed suggestions for improvements, pointing out exactly what should be improved and how, and give examples of other companies doing this better. Rank the improvement ideas by expected impact and implementation effort. If you're suggesting new elements to be added or existing ones to be re-designed, please provide mockups and detailed copy examples we can use as a starting point (in line with the existing tone of the Linear homepage) </structure & content>

<instructions> Please combine insights derived directly from other SaaS companies' pricing pages with best practices discussed in leading industry blogs. Aim for ~3,000 words for the report </instructions>
<goal> Please put together an in-depth analysis of Linear's pricing page (http://linear.app/pricing), critiquing its effectiveness and highlighting where 1) it adheres to industry best practices, 2) it stands out via innovative ideas and 3) where it falls short. </goal>

<structure & content> After a general review of the page, please provide detailed suggestions for improvements, pointing out exactly what should be improved and how, and give examples of other companies doing this better. Rank the improvement ideas by expected impact and implementation effort. If you're suggesting new elements to be added or existing ones to be re-designed, please provide mockups and detailed copy examples we can use as a starting point (in line with the existing tone of the Linear homepage) </structure & content>

<instructions> Please combine insights derived directly from other SaaS companies' pricing pages with best practices discussed in leading industry blogs. Aim for ~3,000 words for the report </instructions>
<goal> Please put together an in-depth analysis of Linear's pricing page (http://linear.app/pricing), critiquing its effectiveness and highlighting where 1) it adheres to industry best practices, 2) it stands out via innovative ideas and 3) where it falls short. </goal>

<structure & content> After a general review of the page, please provide detailed suggestions for improvements, pointing out exactly what should be improved and how, and give examples of other companies doing this better. Rank the improvement ideas by expected impact and implementation effort. If you're suggesting new elements to be added or existing ones to be re-designed, please provide mockups and detailed copy examples we can use as a starting point (in line with the existing tone of the Linear homepage) </structure & content>

<instructions> Please combine insights derived directly from other SaaS companies' pricing pages with best practices discussed in leading industry blogs. Aim for ~3,000 words for the report </instructions>

```

它对定价页面进行了详细剖析，并准确指出了许多只需付出少量投入就能改进的地方；例如：

*   突出显示年度计划的节省金额
    
*   添加每个计划适合哪些用户的描述
    
*   突出显示推荐的 / 最受欢迎的计划
    
*   添加更多 / 更好的工具提示和常见问题部分
    

然而，这也充分显示了 Deep Research 当前的局限性。ChatGPT（与我使用过的其他工具类似）无法使用年度 / 月度定价切换按钮，并（错误地）认为没有月度选项。同样，它也「看」不到页面上滚动的客户 logo。

在我看来，这不是个大问题，因为只需几秒钟就能确认这些观点是否准确，你可以直接忽略不准确的建议。但如果你对此感到困扰，可以使用 Agent Mode，在这种模式下， AI 会实际与网站进行交互并截取屏幕截图，从而避免这类错误结论。不过，你需要等待更长时间才能拿到报告。

#### 用例 4：**分析竞争对手的产品功能**

*   最佳工具：ChatGPT Deep Research ；
    
*   亚军：Gemini Deep Research
    

对于那些正在不同解决方案之间权衡的高意向买家而言，客户比较页面是极具说服力的资源。随着答案引擎优化（AEO）的兴起，这类页面变得更加重要。

但如果你想创建这类页面，或是投放强调产品功能优势的广告，你需要进行大量的研究。

查看竞争对手的网站、阅读官方文档和帮助文章、观看 YouTube 教程等，很容易就会花费数天时间，而且若想确保论断的准确性，这些步骤几乎无可避免。

幸运的是， Deep Research 在这方面表现相当不错。如果从零开始，我建议首先向 Claude、Perplexity 或 Grok 发出一个高层次的提示；它们不会像 ChatGPT 或 Gemini 那样深入，但你会很快得到一份格式清晰的、关于最重要主题的摘要。

```
<goal> I work at [Company] and want to understand how our product compares to [Competitor]. Please compile a detailed report comparing features of both platforms and highlighting any gaps on either side. </goal>

<sources> Please prioritize primary sources that contain facts; i.e. don't rely on anybody's interpretation of what the products can do, but rather focus on official documentation, feature announcements etc. Use in-text citations for ANY claims you make </sources>

<instructions> Make sure to check that any product gaps you’re highlighting still exist; e.g. if you find a report from a year ago that claims a feature is missing, conduct a search to see if it was addressed in the meantime </instructions>
<goal> I work at [Company] and want to understand how our product compares to [Competitor]. Please compile a detailed report comparing features of both platforms and highlighting any gaps on either side. </goal>

<sources> Please prioritize primary sources that contain facts; i.e. don't rely on anybody's interpretation of what the products can do, but rather focus on official documentation, feature announcements etc. Use in-text citations for ANY claims you make </sources>

<instructions> Make sure to check that any product gaps you’re highlighting still exist; e.g. if you find a report from a year ago that claims a feature is missing, conduct a search to see if it was addressed in the meantime </instructions>
<goal> I work at [Company] and want to understand how our product compares to [Competitor]. Please compile a detailed report comparing features of both platforms and highlighting any gaps on either side. </goal>

<sources> Please prioritize primary sources that contain facts; i.e. don't rely on anybody's interpretation of what the products can do, but rather focus on official documentation, feature announcements etc. Use in-text citations for ANY claims you make </sources>

<instructions> Make sure to check that any product gaps you’re highlighting still exist; e.g. if you find a report from a year ago that claims a feature is missing, conduct a search to see if it was addressed in the meantime </instructions>

```

这会让你对产品的潜在优势有一个初步的判断。然后，你可以向 ChatGPT 发出更具体的提示，要求获得关于特定功能的详细信息。

拿到深度报告后，你可以进一步要求解释，或对与你认知不符的论断提出质疑，直到你对这份比较分析完全信服为止。

最后，你还可以让 AI 为你提供建议，告诉你如何将这些洞察转化为一个有竞争力的产品比较页面：

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDs8gBoQuYDgvb6VsNwBsrODjib917h16MAjZWyP2oCIwf8cbAB3eNKLpQ/640?wx_fmt=png&from=appmsg)

比较 FP&A 平台 Runway 和 Pigment 的完整示例报告：https://chatgpt.com/s/dr_689a597a84588191afe66270d8f6074f

**需要注意的主要事项：**

*   产品变化频繁，因此你务必需要确保任何主张都基于最新信息。这意味着：
    

*   在提示词中指示研究代理优先采用最新来源，并重点关注过去 6 个月内的信息（如上例所示）
    
*   通过快速的 Google 搜索，再次确认最重要的论断是否依然准确。
    

*   无论你的初始提示写得多好， AI 往往会引用模糊的营销主张，如「卓越的 AI 能力」。当出现这种情况时，我建议你进一步追问，要求提供详细示例；通常第二版的回答会好很多。
    

#### 用例 5：国际扩张的市场评估

最佳工具：GPT-5 思维版 / Claude Opus（用于框架和数据源）；ChatGPT Deep Research （用于最终报告）

每个初创公司迟早都要应对国际化问题。但应该先进入哪些国家，按什么顺序扩张呢？

对此，我推荐一种两步法：

1.  首先，选择你喜欢的 AI 模型（如 GPT-5 或 Claude Opus），协助制定扩张框架并寻找高质量的数据源；
    
2.  然后，让 ChatGPT Deep Research 为你创建一份详细的报告，对你提出的各个维度进行潜在国家的排名；
    

一般来说， Deep Research 的设计初衷是完成所有这些工作，无需第一步，但实际上，我发现如果能提供这些指导， Deep Research 能产生更好的结果。

让我们先建立框架。如果你已经有了一个思路，描述出来，让 AI 对你的推理提出挑战。如果没有，请让它和你一起 brainstorm 一些不同的思维模型。（这是 ChatGPT 的一个示例回答）

```
<goal> Please help me develop a framework for stack ranking markets for international expansion, outlining different angles from which this can be framed and proposing a comprehensive framework that combines the most important ones. </goal>

<context> We’re [context on your company]. After scaling in the US, we're looking to expand internationally. I'm thinking [outline your current thoughts on internationalization], but I'd like you to help me think through this more holistically </context>
<goal> Please help me develop a framework for stack ranking markets for international expansion, outlining different angles from which this can be framed and proposing a comprehensive framework that combines the most important ones. </goal>

<context> We’re [context on your company]. After scaling in the US, we're looking to expand internationally. I'm thinking [outline your current thoughts on internationalization], but I'd like you to help me think through this more holistically </context>
<goal> Please help me develop a framework for stack ranking markets for international expansion, outlining different angles from which this can be framed and proposing a comprehensive framework that combines the most important ones. </goal>

<context> We’re [context on your company]. After scaling in the US, we're looking to expand internationally. I'm thinking [outline your current thoughts on internationalization], but I'd like you to help me think through this more holistically </context>

```

然后，我们将编制一份市场数据的高质量来源清单。（这是 ChatGPT 的一个示例回答）

```
I'm looking to do the actual stack ranking of markets in Deep Research. Please compile a list of potential high-quality data sources for 1) TAM and 2) Competition data.

Please list out different sources and compare them across criteria like 1) what exact data cuts they contain, 2) how credible they appear (and why; e.g. data from primary sources like statistical bureaus and government organizations should be rated higher than blogs / random websites), 3) how recent the data is etc. Please also categorize them by access (free vs. paid vs. requiring a free account / login).
I'm looking to do the actual stack ranking of markets in Deep Research. Please compile a list of potential high-quality data sources for 1) TAM and 2) Competition data.

Please list out different sources and compare them across criteria like 1) what exact data cuts they contain, 2) how credible they appear (and why; e.g. data from primary sources like statistical bureaus and government organizations should be rated higher than blogs / random websites), 3) how recent the data is etc. Please also categorize them by access (free vs. paid vs. requiring a free account / login).
I'm looking to do the actual stack ranking of markets in Deep Research. Please compile a list of potential high-quality data sources for 1) TAM and 2) Competition data.

Please list out different sources and compare them across criteria like 1) what exact data cuts they contain, 2) how credible they appear (and why; e.g. data from primary sources like statistical bureaus and government organizations should be rated higher than blogs / random websites), 3) how recent the data is etc. Please also categorize them by access (free vs. paid vs. requiring a free account / login).

```

最后，我们将所有这些输入到 Deep Research 中，得到一份按排名排序的国家列表：

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3ugBaRmFvLlibXfbqDezPdDsG11uqx9hiaWVPC6X2HYOqzicdI8GibSyiaADZD7aPDjMYicf2T7qOqrF3aA/640?wx_fmt=png&from=appmsg)

完整报告：https://chatgpt.com/s/dr_68980ca1e9748191bf51024236d51852

**05**
------

**更多关于 Deep Research 的灵感**
--------------------------

以上示例只是 Deep Research 能做的一部分事情。其可能性几乎是无限的，但在这里一一列举会使本文篇幅过长。

不过，这里有一些更多的想法供你尝试：

*   使用 ChatGPT agent mode，来记录领先公司或你的竞争对手是如何处理产品演示预约或用户入职等流程的；
    
*   使用 Perplexity 快速了解社交媒体对你最近发布内容的反馈；
    
*   让 ChatGPT Deep Research 整理一份详尽的报告，介绍与你公司类似的公司所使用过的成功营销手段和增长技巧，然后与推理模型（GPT-5 或 Claude Opus）合作，确定哪些对你来说是有意义的，以及如何进行调整。
    

![](https://mmbiz.qpic.cn/sz_mmbiz_png/qpAK9iaV2O3sVEDaEXOSIu0FvvT1ahtsFuSMmBOmKmEicRE9EksiaO6CM0Aj3HLXJicHNEDEMrYmgqiaibfQ0k1Balaw/640?wx_fmt=png&from=appmsg&tp=webp&wxfrom=5&wx_lazy=1)

**更多阅读**

[Cursor 的困境：它真的找到 PMF 了吗？](https://mp.weixin.qq.com/s?__biz=Mzg5NTc0MjgwMw==&mid=2247518639&idx=1&sn=fb085448a210930114f1a8f38f269cc2&scene=21#wechat_redirect)

[7 亿用户白嫖 ChatGPT，OpenAI 怎么从他们身上赚到钱？](https://mp.weixin.qq.com/s?__biz=Mzg5NTc0MjgwMw==&mid=2247518634&idx=1&sn=77f07d925b707634f8db9bd3043f54ab&scene=21#wechat_redirect)

[从 0 到 1 做一款 AI 产品：技术怎么搭、成本如何控制、销售策略怎么定？](https://mp.weixin.qq.com/s?__biz=Mzg5NTc0MjgwMw==&mid=2247518604&idx=1&sn=3f693e6d585bfe47b5a1458e44e9f985&scene=21#wechat_redirect)

[7 亿用户白嫖 ChatGPT，OpenAI 怎么从他们身上赚到钱？](https://mp.weixin.qq.com/s?__biz=Mzg5NTc0MjgwMw==&mid=2247518634&idx=1&sn=77f07d925b707634f8db9bd3043f54ab&scene=21#wechat_redirect)

[一个半月高强度 Claude Code ：Vibe coding 是一种全新的思维模式](https://mp.weixin.qq.com/s?__biz=Mzg5NTc0MjgwMw==&mid=2247518512&idx=1&sn=c3c97b1980ee59ae048229bc0a2e8d1a&scene=21#wechat_redirect)

转载原创文章请添加微信：founderparker