# 视频理解与内容提取
该项目旨在基于百炼平台和对象存储OSS，借助大模型能力用户能快速构建部署自动化信息提取应用，实现对视频信息提取。

## 功能特点
- 支持视频文件上传，自动抽取视频帧，视频帧图片自动存储到对象存储OSS中。
- 支持百炼模型服务调用，实现视频帧序列图片信息提取。
- 支持鉴权访问，默认关闭（生成环境中部署建议开启鉴权访问）。


## 环境准备

确保你的系统已经安装了 Python3.10 语言环境。

克隆或下载此项目：

```sh
git clone git@atomgit.com:aliyun_solution/video-information-extraction.git
cd video-information-extraction
```

安装项目依赖：

```sh
pip install -r requirements.txt
```

## 环境变量

- `DASHSCOPE_API_KEY`：百炼的 API-KEY，获取方式请参考：[如何获取](https://help.aliyun.com/zh/model-studio/developer-reference/get-api-key "如何获取")。
- `ALIBABA_CLOUD_ACCESS_KEY_ID`：访问对象存储OSS发起请求，获取方式请参考：[如何获取](https://help.aliyun.com/zh/oss/developer-reference/use-the-accesskey-pair-of-a-ram-user-to-initiate-a-request "如何获取")。
- `ALIBABA_CLOUD_ACCESS_KEY_SECRET`：访问对象存储OSS发起请求，获取方式请参考：[如何获取](https://help.aliyun.com/zh/oss/developer-reference/use-the-accesskey-pair-of-a-ram-user-to-initiate-a-request "如何获取")。
- `OSS_ENDPOINT`：对象存储外网访问 Endpoint（地域节点），获取方式请参考：[如何获取](https://help.aliyun.com/zh/oss/user-guide/oss-domain-names "如何获取")。
- `OSS_BUCKET`：对象存储存储桶名。
- `ENABLE_LOGIN`：开启鉴权访问（默认为 `false`）。
- `USER_NAME`：应用程序的用户名（默认为 `""` ENABLE_LOGIN 为 `true` 时需要配置）。
- `USER_PASSWORD`：应用程序的密码（默认为 `""` ENABLE_LOGIN 为 `true` 时需要配置）。

## 运行

设置环境变量并运行项目：

Linux/Mac


```sh
export DASHSCOPE_API_KEY=<百炼的 API-KEY>
export ALIBABA_CLOUD_ACCESS_KEY_ID=<访问对象存储OSS发起请求的 ALIBABA_CLOUD_ACCESS_KEY_IDY>
export ALIBABA_CLOUD_ACCESS_KEY_SECRET=<访问对象存储OSS发起请求的 ALIBABA_CLOUD_ACCESS_KEY_SECRET>
export OSS_ENDPOINT=<对象存储外网访问 Endpoint（地域节点）>
export OSS_BUCKET=<对象存储存储桶名>
export ENABLE_LOGIN=<是否开启鉴权访问，可选>
export USER_NAME=<示例应用登录用户名，可选>
export USER_PASSWORD=<示例应用登录密码，可选>

python app.py
```

或者在 Windows 上：

```cmd
set DASHSCOPE_API_KEY=<百炼的 API-KEY>
set ALIBABA_CLOUD_ACCESS_KEY_ID=<访问对象存储OSS发起请求的 ALIBABA_CLOUD_ACCESS_KEY_IDY>
set ALIBABA_CLOUD_ACCESS_KEY_SECRET=<访问对象存储OSS发起请求的 ALIBABA_CLOUD_ACCESS_KEY_SECRET>
set OSS_ENDPOINT=<对象存储外网访问 Endpoint（地域节点）>
set OSS_BUCKET=<对象存储存储桶名>
set ENABLE_LOGIN=<是否开启鉴权访问，可选>
set USER_NAME=<示例应用登录用户名，可选>
set USER_PASSWORD=<示例应用登录密码，可选>

python app.py
```

## 测试

本地访问地址 `http://localhost:9000` 。

## 常见问题
1、windows 运行时出现以下错误提示，可以使用命令`pip install --upgrade openai`来更新`openai`库版本。
```
TypeError: Client.__init__() got an unexpected keyword argument 'proxies'
```

## 接口变更说明
- `/api/completions` 拆分为两个独立接口：
  - `POST /api/vision-analysis` 视觉模型分析
  - `POST /api/behavior-analysis` 儿童行为分析
- 前端增加分步操作按钮，需先完成视觉分析才能进行行为分析

