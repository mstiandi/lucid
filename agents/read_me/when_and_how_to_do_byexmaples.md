## 做一个简单的工作图：
用户上传PC端复制的聊天记录 
--- 系统 --- 构建聊天数据库

            |

同时，用户提出“我很爱她，但是她拒绝我了，我很难受” 
--- signal_agent --- 分析聊天记录，标出指标（双方的信号强度、清晰度、主动性等等），供后续agent分析
--- evidence_agent --- 找事实、找证据 => 你凭什么认为她拒绝你了？证据是你自己脑部的？观察推理的？还是她直接跟你说了：老子讨厌你，滚一边去，别烦我？
--- information_symmetry_agent ---  识别想法：我爱她 => 提出信息对称性：她知道你爱她嘛？
--- feedback_asymmetry_agent --- 【这里似乎用不到】
--- contradiction_registration_agent --- 寻找矛盾点：我的结论（她拒绝我） => 事实：没有明确表明（这里可以跳到alternative_explanation_agent） 
--- alternative_explanation_agent --- 你爱她？你释放的所有信号都有可替代性解释：写信 -- 她母亲的示意、你的任务、你自己的情绪倾诉（垃圾桶）。 她拒绝你？她的不主动会不会是因为她含蓄内敛？希望明确心意坦白？



## 进一步分析：
其实这六个agent不应该在这个用户的初次对话就全部调用，我们应该有一个懂大局的supervisor，统筹聊天进程。
比如：第一轮对话，用户上传聊天记录，那么supervisor的提示词就会让它将这个聊天记录交给signal_agent，让它做一个信息数据库，同时返回它该返回的JSON分析，回到supervisor，summary，整理messages（还是results?）后，END，回答用户。

然后第二轮对话，用户说：“我很爱她，但是她并不喜欢我”，supervisor提取了两个结论（信念） --- “我爱她”和“她不爱我”
"""以下两个agent应该并行处理，不应该用串行"""
--- 交给evidence_agent，找证据，验证或者反驳这两个东西 --- 找到后，质问用户为什么这样认为，你是基于什么这样认为的，在系统分析看来，有如下evidence可以反驳你的观点。
--- 交给information_agent，信息对称嘛？她知道我爱她嘛？这个可以用一个state参数存储，不一定需要立刻和用户反馈这个agent返回的信息。

然后第三轮对话，用户说了自己之前基于什么进行上述判断的，同时对我们的分析表示一定的认同，然后supervisor判定需要：
"""依旧采用并行处理多agent"""
--- 交给contradiction_registration_agent --- 注册矛盾，应该用一个state参数，注册“她不喜欢我”这个结论和事实的矛盾
--- 交给alternative_explanation_agent --- 说明用户有很多自以为爱的表述、暗示都是可被替代性解释的，她的一些回答也并不一定是拒绝或者是没有好感，可能是性格驱使的

然后进行下面的聊天，等等。



## 基于上述我的梳理，我发现几个问题：
1.supervisor怎么判断什么情况该交给什么agent，一个还是多个？ --- 感觉可以用prompt加上一个交接tool进行处理
2.不同阶段为什么交给不同的agent？不同agent到底什么时候启动？返回的到底是messages直接作用于回答，还是特定的state参数，进行存储，不急于回答？
3.感觉整个聊天过程没有太多我们系统引导用户的感觉，如果什么都让用户自己说的话，是不是有点累啊？ --- 可以在END前加一个引导节点，基于messages，对和用户的下一轮对话进行引导，可以在回答的末尾显现，不过这个节点似乎也得设计一个和整个系统相关的提示词或者工具，要能知道我们的系统是啥样的，好做出合理的引导。



## 基于上述陈述，我们进行下一步设计
"""state 状态参数"""
class JokerState(TypedDict):
    messages: Annotated[list, add_messages]
    next_agents: list  # 由supervisor判断下一步需要并行调用的agents
    route: Annotated[list[list], add_list] # 各个step并行调用的agents，进行存储，len长度就是分析轮次
    contradictions: Annotated[dict, add_dict] # 记录矛盾 key:结论, value:事实list[str]
    still_contradictions: Annotated[dict, add_dict] # 记录矛盾是否已经被用户解决，key:结论, value:done?
    chat_info: dict # 聊天记录信息，{"role": "user_chat_id", "info": "...", "role": "ta_chat_id", " "}


"""supervisor 如何决定调用什么agent？"""
--- 设计一个parse_intention() tool ---
这个工具对于HumanMessage进行各项分析，应该有一个特定的prompt设计，这里定义为parse_intention_prompt。
分析用户的信息是否有结论（观点），如果有，类似“她不喜欢我”这样的，那么返回中就应该有键值对：
{"viewpoints": [...], }


--- 设计一个parse_change() tool --- 
首先检测still_contradictions进行筛选，然后和messages[-2] -- AIMessage中的矛盾进行“与”，提取这轮对话提到的矛盾，然后根据messages[-1] -- HumanMessage 分析用户对于某些我们提出的矛盾是否有改观，是否发觉并认同，比如：“哦哦哦，确实有这个可能”。
同样的应该有一个特定的prompt，定义为parse_change_prompt。

发现一点问题：
1. supervisor干的活不止next_agents的决定了，到底他的职责是什么？
2. 有点乱，而且分析的很浅，6个agent的分析还没有头绪，他们需要的state参数呢？返回的参数呢？相互的edge呢？


