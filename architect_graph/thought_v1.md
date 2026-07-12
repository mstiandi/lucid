## 6个agent分化细化

## 全局JokerState
class JokerState(TypedDict):
    messages: Annotated[list, add_messages]
    all_signals: Annotated[dict, add_dict_reducer1] # key 两个，即双方，value一个dict
    all_claims: Annotated[list[list], add_list_list_reducer] # 这个是list嵌套list再嵌套str
    all_evidences: Annotated[dict, add_dict_reducer2] # {claim: {evidence1: {content:.., score:.. }}}
    alternative_explanations: Annotated[dict, reducer] # {claim:{youthink:content,alter:explanation}}
    info_symmetry: Annotated[dict, reducer] # {claim:{from:user_or_ta, user_know:bool, ta_know:bool}}
    next_agents: list
    contradictions: Annotated[dict, reducer] # {claim: contradiction_reason}
    changed_contradictions: list


## Graph工作流设计
用户信息进来，
     |
（我觉得信息预处理节点可以做一个tool，给supervisor调用，就是在supervisor的提示词中明确每次必须调用这个tool进行信息分析）
tool返回的结果schema如下:
new_signal: bool 
new_claim: bool
claim_direction: Literal[both, single]
claim: list[str]   # 用户自己表达的观点，比如：“她不喜欢我”。一轮对话的claim可能不止一个，所以用list[str]
changed_contradictions: list[str]   # 用户发觉的我们提出的矛盾，并认可了
     |
然后判定得交给哪些agent：
如果new_signal判定为True，那么直接交给signal_agent，让signal_agent进行信号处理后，交给，再根据claim继续；

如果new_claim判定为True，这个claim应该被判定成单向的还是双向的，不同的情况需要不同的graph策略，具体调用应当如下：
single：我表达了自己的心意 -- 单向表达 -- evidence_agent -> contradiction_registration_agent
                                  -- alternative_explanation_agent （evidence和alternative的结果合并后交给contradiction进行注册登记）

single：她暗示过她没有好感 -- 单向表达 -- 同上

both：我觉得她对我没意思 -- 双向推测 -- evidence_agent -> contradiction_registration_agent
                                  -- alternative_explanation_agent（同上）
                                  -- information_symmetry_agent（并行）
                                  -- feedback_asymmetry_agent（并行）




## 至此，整体思路相对清晰了，下面进行文字说明：
首先是以一轮用户和我们的系统的对话为最小跑全graph单位，如下：
用户HumanMessage -> supervisor(parse_tool) -> schema -> agents -> answer
signal_agent返回schema，额，应该直接关联全局JokerState比较好：
{"new_signal": False, "all_signals": {"user":{"":"",...}, "ta":{"":"",...}}}

如果supervisor判定new_signal，那么signal_agent返回的结果，会消除new_signal这个死循环，然后返回可追加的signal，更新all_signals

然后supervisor如果判定new_claim，那么就会并行同时进行evidence_agent和alternative_explanation_agent，然后这两个的返回会更新全局JokerState，然后contradiction_registration_agent会根据更新的JokerState进行分析，这三个绑在一块，然后同时和information_symmetry_agent并行，和feedback_asymmetry_agent并行，跟个电路似的，最后全部汇聚到一个节点（reflexion或者summary）

然后剩下的就是讨论这5个agent（除signal_agent已经确定好了）的各自返回schema以及互通关系了
--- evidence_agent --- 
首先是evidence_agent，针对本轮claim，从all_signals中找evidence，返回的直接更新于all_evidences，注意全局JokerState的all_evidences的schema：具体哪一个claim(str)的，什么content，对claim有多少验证度分数score(1-10，低于5是反驳，高于5是证实，这个可以写进evidence_prompt中)

--- alternative_explanation_agent --- 
根据all_signals判定用户可能是基于什么信号做出这个claim的，然后重新判定这个signal会不会有alternative_explanation，返回的应该是更新全局的JokerState的alternative_explanations

--- contradiction_registration_agent --- 
根据evidence_agent找到的evidence分析，和alternative_explanation_agent找的的alternative_explanation
进行对claim的矛盾检测，检测claim和事实是否存在关键矛盾，返回的对应全局JokerState中的contradictions，说明哪一个claim我们判定是矛盾的，dict的value就是判定矛盾的原因

--- information_symmetry_agent --- 
根据new_claim == True，到claim_direction == both，到了这里。
分析信息是否对称，从all_signals中找寻信息，判定，返回的值更新，同理

--- feedback_asymmetry_agent --- 
与上 同理

## 几个问题
1. 很多agent的返回值都是直接和claim挂钩的，但都是独立的一个JokerState参数，我在想能不能融入all_claims参数中，直接给all_claims中的每一个claim进行一个dict，多个键值对，但是感觉现在不行，首先是all_claims的第一层解码不是str而是list，其次，不同键值对的schema差距似乎存在，不适合同时塞入一个dict。

2. 关于对称性，这个似乎不一定能在当轮就判定完成，可能用户没有提供完整的signals，可能要将这个对称性加一个能否基于当前all_signals进行充分判定的参数，如果行，那直接在本轮回答，如果不行，那就在回答中问用户，“你说的：...，她知道嘛？”，这里还有一个细节，就是她说的什么，我现在肯定是对称的，但是当时未必，可以参考我和Jenny的志愿问题的那个事，不过这个分析应该就是基于当时的，所以这个还是判定为不对称

3. supervisor感觉管理这么多很麻烦，我看到evidence_agent、alternative_explanation_agent并行后串行contradiction_registration_agent这个小体系，能不能在内部打通？比如在前两者返回值中用Command命令，直接goto第三者？但是这样的return会不会导致原本的返回信息被挤出？

4. 其次还有changed_contradictions这个，我都忘了，但是回过头想想，感觉这个判定似乎没啥具体作用吧？就算有用，也就是在JokerState添加一个参数，表示那些contradictions已经被共识，那些待解决，但是这玩意，就是changed_contradictions本身就很难判断，毕竟用户不会一个一个说：“我认同你说的矛盾”，很多时候都是静默吧？我们不能猜。就算可以，那么剩下的agent对于contradiction的分析都要基于是否changed这个参数进行筛选分析的，这样的复杂度拉高了，现在还没到这么细致的时候，这个完全可以放以后讨论，或者直接当作边际效益，忽视。

5. 上面的架构我写了一个多小时，累了，不过感觉整体顺下来对我的一些思维还是有提升的，比如如何设计state及schema，不同的agent关系，怎么决定next_agents，不同的agent返回的schema及其对其他部分工作的作用。挺累的，但是收获是有的



## 修订
1. all_signals 的 schema:
{"user": {"initiative_score",
          "emotional_explicitness":,
          "signal_clarity":,
          "behaviors":[
               {"action":"写信","signal_type":"indirect_expression","confidence":0.7},
          ]}}
问：需要原始内容嘛？还是只要总结的behaviors参数/

2. feedback_asymmetry暂时砍掉

3. all_claims的schema，同时牵扯到supervisor的tool的claim参数的schema:
claim:list[dict] 一轮对话用户可能表达多个claim，每单个claim的schemma是dict：
{"content":
 "direction":}
感觉有问题，这个似乎不能作为supervisor的tool使用，应该直接当作预处理节点的
我重新设计了一下

                           (all_signals)
                          -> signal_node               evidence     -> contradiction  
START -> preprocess_node                       -> 块  alternative
     (new_signal,all_claims)        -> supervisor                                 -> summary -> END
                                                -> infomation


回到claim的问题，现在没有claim参数，这个tool，只有全局的JokerState的all_claims参数
list[dict]，每一个dict就是一个claim，内部有其余判断参数
[{"content":str,
  "direction":Literal[single, both],
  "analysed_by":list, # 由谁分析过，这个比bool的简单判断是否分析过更合适
  "status":Literal["pending", "analysed"],
  "evidence_from_signals":{"evidence1":{"content":,"credit_score":},"evidence2":{},}, 
  "alternative_explanations":{"one_of_evidence":{"youthink":,"alternative":},""}
   },{}]

## 修订后的结构
开始，然后预处理节点提新的claim，更新all_claims，交给后续supervisor决定给谁
预处理节点同时判断是否有新的signal，如果有直接交给signal_node，然后signal_node在交给supervisor
然后就到了supervisor，根据all_claims的status确定是否需要派发，若为analysed就再根据direction进行派发，
每一个派发的子agent，处理后的return都要更新analysed_by参数，防止重复，也方便记录

我又更新了all_claims参数，现在是相当于将evidence节点和alternative节点都并入all_claims参数了，这样或许更方便分析

然后contradiction节点根据前两者的返回进行矛盾登记，独立的参数JokerState:contradictions
这里就会出现一个处理细节，就是这个节点只分析analysed_by中没有被它分析过的claim

同时也是根据direction是否为both，选择是否交给information节点

最后的summary，到此时，status都应该是pending，过了summary才能改为analysed
对pending的claim进行分析，根据evidence参数和alternative参数，总结一点，
再根据contradition总结一点，我怎么感觉这玩意也能并入all_claims？如果不并入怎么确保不混淆呢？并入的话似乎好点
再根据information_symmetry总结一点，难道这个也可以并入？
这两个不并入，我担心的就是怎么不和前面已有的弄混淆，怎么确保summary分析的就是本轮对话的？
我想着能不能通过并入，通过status参数进行简单判别然后分析？但是总感觉并入会不太好

还有一个问题，就是要不要加一个reflexion节点？但是它怎么判断是否充足呢？



## 再修订
# info_symmetry 写入 JokerState
{
     "claim_content":{
          "from": "user",
          "user_knew": True,
          "ta_knew": None,          # 无法判断
          "is_sufficient": False,   # ← 这个
          "missing_info": "需要知道她是否知道用户写了信"
     }
}

  is_sufficient=False → summary 在回答末尾追问用户。is_sufficient=True → summary 直接给出结论。

  不需要单独的 reflexion 节点。确定性逻辑不该用 LLM 做。

class JokerState(TypedDict):
    messages: Annotated[list, add_messages]
    # 信号数据库（signal_node 写入）

    all_signals: Annotated[dict, add_dict_reducer]
    # {"user": {"initiative_score": float, "emotional_explicitness": float,
    #           "signal_clarity": float, "behaviors": [...]},
    #  "ta": {...}}
    # 声明列表（preprocess_node 新增，各 agent 扩充）

    all_claims: Annotated[list[dict], add_list_reducer]
    # [{"content": str, "direction": "single"|"both",
    #   "analysed_by": [...], "status": "pending"|"analysed",
    #   "evidence_from_signals": {...}, "alternative_explanations": {...}}]
    # 矛盾注册（contradiction_node 写入，跨 claim）

    contradictions: Annotated[dict, add_dict_reducer]
    # {"claim_content": "矛盾原因"}
    # 信息对称性（info_symmetry_node 写入）

    info_symmetry: Annotated[dict, add_dict_reducer]
    # {"claim_content": {"from": str, "user_knew": bool,
    #                    "ta_knew": bool, "is_sufficient": bool}}
    # 路由控制

    next_agents: list


# workflow
  START → preprocess_node
             │
             ├── new_signal=True → signal_node 
             │                           |
             └── new_signal=False → supervisor
                                         │
                                     supervisor 看 all_claims[pending]
                                         │
                                     ┌───┴───┐
                                evidence   alternative  (并行)
                                     └───┬───┘
                                         │
                                    contradiction
                                         │
                                (direction=both?)
                                 ├─ Yes → info_symmetry → summary → END
                                 └─ No  → summary → END

## 问题
1. 就是evidence节点和alternative节点因为寄生于all_claims参数，这就导致这两个节点的返回的dict：
{"all_claims":{
     "content": XXXX
}}

这个content必须和原来的验证的或者进行替代性解释的Claim的content完全==，否则就会直接当成新的Claim来处理了
但是这个如何能保障呢？LLM的prompt还有tool都无法完全限制!

改法：
待定？

2. summary入边节点深度不同
如果information节点不经过contradictory节点，而是直接到summary，那么与之并行的evidence和alternative节点和information的深度就不同，就会导致summary一次调用返回的不完整，必须进行两次调用，显然不是上策。

改法；
evidence, alternative, information并行，然后都到contradictory节点
然后再由contradictory交给summary节点，
如下图所示，新的架构图
  supervisor ══(条件边, 按 next_agents 列表)══▶ evidence
                                            ├─▶ alternative_explanation
                                            └─▶ information_symmetry
                                                      │
          evidence ─────────┐                         │
          alternative ──────┼──(静态边)──▶ contradictory ◀──(静态边)─┘
                            │                    │
                            └────────────────────┘
                                                 ▼
                                              summary ──▶ END
