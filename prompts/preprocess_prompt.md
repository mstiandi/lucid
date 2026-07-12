## 预处理提示词
你要根据用户发送的信息（HumanMessage）提取并返回new_signals和claims两个参数，
new_signals:bool，判断用户发送的信息中有没有出现新的信号，即有无用户和对方的互动说明，不用具体分析什么signal，只需要判别是否有新的signal就行
claims:list[Claim]，判断用户发送的信息中是否出现用户新表达的claims，Claim的schema如下：
class Claim(TypedDict):
    content: str   # claim的内容，用户具体表达了什么
    direction: Literal["single", "both"]  # 用户表达的这个claim是单方面的一方到另一方还是双方互动的
    analysed_by: list[str]  # 经过了什么节点的分析，初始情况为空列表：[]
    status: Literal["pending", "analysed"]  # 初始情况为pending
    evidence_from_signals: dict[str, EvidenceItem]  # 初始情况为空字典：{}
    alternative_explanations: dict[str, AlternativeItem]  # 初始情况为空字典：{}


## 事例，包含四种可能的情况
事例1：有signal，有claim
用户："她和我一起去黄山旅行过，我认为她对我有好感"
返回：{"new_signals": true, "claims": [{"content": "对方对自己有好感", "direction": "both"}]}

事例2：有signal，无claim
用户："昨天她主动给我发消息了"
返回：{"new_signals": true, "claims": []}

事例3：无signal，有claim
用户："我觉得她根本不在乎我"
返回：{"new_signals": false, "claims": [{"content": "对方不在乎自己", "direction": "both"}]}

事例4：都没有
用户："好的，我知道了"
返回：{"new_signals": false, "claims": []}

注意：claims 中只需要返回 content 和 direction 两个字段，
analysed_by、status、evidence_from_signals、alternative_explanations
由代码自动填充初始值，不需要你返回。