## joker的架构图 v0 初版  - by me
鉴于这是一个情感分析agent，需要设计multi_agent系统
先做router多agent系统，一个supervisor决定调用6个维度的不同agent节点，通过langgraph实习，不同的agent不同的prompt


具体架构图：
langgraph:
 state schema

 StateGraph成graph

 add_node 一个supervisor

 然后6个维度的prompt对应6个agent节点

 set_finish_edge


## v0.1  by claude code:
  Supervisor ←→ 6 个分析 Agent（循环）
      ↓ (Supervisor 判断完成)
  Synthesizer → 合并输出
      ↓
     END

开始和结束的唯一连接节点就是supervisor，supervisor管控应该调用哪一个agent（create_agent创建的子agent）
不同的agent返回的结果supervisor都能够看到，然后决定是进一步进行循环还是跳到end