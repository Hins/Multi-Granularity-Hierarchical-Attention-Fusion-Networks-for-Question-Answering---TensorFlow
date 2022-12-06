# 基于多粒度层级attention融合的中文阅读理解推理工具

## 目录

+ <a href="#1">功能介绍</a>
+ <a href="#2">上手指南</a>
  + <a href="#3">开发前的配置要求</a>
  + <a href="#4">安装步骤</a>
+ <a href="#5">文件目录说明</a>

## <span name="1">功能介绍</span>

​		基于多粒度层级attention融合的中文阅读理解推理工具，针对中文阅读理解模型输出的结果计算rouge、bleu等指标。这些值越高越 好。输入的格式为 .json 输出格式为 .json。参考论文《Multi-Granularity Hierarchical Attention Fusion Networks for Reading Comprehension and Question Answering》

##<span name="2">上手指南 </span>

### <span name="3">开发前的配置要求</span>

arm服务器
colorama
nltk
tqdm
psutil

### <span name="4">安装步骤</span>

pip install -r requirements.txt

## <span name="5">文件目录说明</span>

code
├── README.md ---> 工具说明
├── Dockerfile ---> docker镜像工具
├── /code/ ---> 源代码
│ ├── monitoring.py ---> 监控工具
│ ├── inference.py ---> 推理工具
├── get-pip.py ---> pip安装工具
├── get_started.sh ---> 初始化脚本
├── /model/ ---> 模型文件夹
├── /experiments/ ---> 实验模型
│── requirements.txt ---> 环境安装包信息