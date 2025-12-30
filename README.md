# 工具简介
KAOT（Kunpeng Auto Optimization Tool）是一款系统性能调优工具，其核心目标是通过自动化操作提升调优效率与易用性。相较于传统人工调优，KAOT可根据用户指定的应用场景，自动完成调优配置文件生成、调优配置执行及鲲鹏BoostKit加速库安装等一系列操作，同时用户可以指定特定的调优手段进行快速使能，有效降低手动操作的复杂性和出错风险。

工具使用文档可参考：[通算一体机性能综合调优参考实践](https://www.hikunpeng.com/zh/developer/techArticles/20251222-1)。
# 环境部署
本项目支持源码方式部署，下载代码仓库后，安装所需的Python依赖即可使用。

1. 拉取代码仓库
```
git clone https://gitcode.com/boostkit/kaot.git
```
2. 安装依赖
```
cd kaot
pip install -r requirements.txt
```
3. 验证是否安装成功
执行以下命令，若回显相关帮助信息代表安装成功：
```
python3 kaot.py -h
```
# 快速上手
1. 生成基线文件
```python
python3 kaot.py basecfg
```
基线文件可用于调优项回退，若无需回退，则不需要使用。

2. 根据场景common生成调优配置文件
```python
python3 kaot.py generate -s common -o feature_config.yaml
```
根据执行成功后的日志回显，可查看生成的配置文件feature_config.yaml，确认调优项是否都需要使能。

3. 使能调优项
```python
python3 kaot.py execute -tp feature_config.yaml
```
根据执行打屏日志，可查看生成的基线文件base_config.yaml是否完整、调优项是否执行成功，以及是否需要安装加速库。

4. 使能加速库安装（可选）

根据使能过程中的日志提示，判断是否需要安装加速库软件，若需要按提示进行加速库安装，例如：
```python
python3 kaot.py install -n boostkit_ksl  -d /install_pkgs
```
其中/install_pkgs为软件包放置的目录。

5. 回退不需要执行的调优项（可选）

若要回退指定的调优项，需将基线文件拷贝到kaot/output目录下，并将其中deploy字段修改为Y，然后按调优项使能新生成的配置文件，以回退disable_swap为例，使用方式如下：

（1）获取基线文件
由`execute`子命令使能时会生成基线文件，也可以由子命令`basecfg`直接生成基线文件，基线文件需放置在kaot/output目录下。

（2）修改基线文件
执行以下命令将基线文件base_config.yaml中deploy字段的值修改为Y：
```python
python3 kaot.py generate -bp base_config.yaml -o target_config.yaml
```
（3）执行调优项回退
新生成的配置文件target_config.yaml可直接进行使能，使能即代表回退成基线状态，可通过-f指定要回退的调优项：
```python
python3 kaot.py execute -tp target_config.yaml -f disable_swap
```
# 贡献指南
如果使用过程中有任何问题，或者需要反馈特性需求和bug报告，可以提交issue联系我们，具体贡献方法可参考[这里](https://gitcode.com/boostkit/community/blob/master/docs/contributor/contributing.md)。