# -*- coding: utf-8 -*-
"""
企业级视频分析大模型部署 Flask 应用
========================================
功能：
    1. 用户登录鉴权（简单示例，生产环境建议使用专业认证方案）
    2. 视频上传，调用关键帧提取（保持现有代码），返回关键帧 URL 列表
    3. 并行化视觉分析：将关键帧图片转为 base64 并批量并行调用视觉模型（Qianwen 2.5 VL），再调用文本模型生成视频描述
    4. 调用行为分析生成详细报告
    5. 定时清理旧的关键帧文件

部署环境：部署在4块 A100（40G）服务器上，针对 Qianwen 2.5 VL 模型进行并发优化

依赖：
    - Flask、OpenCV (cv2)、numpy、scenedetect、openpyxl、concurrent.futures
    - OpenAI SDK（或对应百炼模型 SDK）
    - 自定义模块 auth（用于登录鉴权）

注意：
    - 部分敏感信息（如 secret_key、API_KEY 等）建议通过环境变量传入
    - 关键帧提取部分不做改动，其余部分重点提升并发性能和健壮性
"""

import os
import json
import cv2
import numpy as np
import shutil
import base64
import random
import time
import logging
import tempfile
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, session
from werkzeug.utils import secure_filename
from openpyxl import load_workbook
from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector
from openai import OpenAI  # 假设 OpenAI SDK 适配百炼模型服务

# 导入自定义认证模块（请确保 auth.py 存在且实现 auth_login）
from auth import auth_login  # 此处 require_login 将在本文件中重新定义

# ================================
# 日志配置
# ================================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ================================
# Flask 应用初始化及配置
# ================================
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'wefwef43543t435y54y345wy45wy564y')

# 配置上传目录和关键帧存储目录
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['KEYFRAMES_FOLDER'] = os.path.join(os.getcwd(), 'static', 'keyframes')
# app.config['ALLOWED_EXTENSIONS'] = {'mp4'}

# 确保目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['KEYFRAMES_FOLDER'], exist_ok=True)

# ================================
# API 客户端初始化（百炼模型服务）
# API 客户端初始化（百炼模型服务）
# ================================
vl_client = OpenAI(
    api_key=os.getenv('VL_API_KEY', 'EMPTY'),
    base_url=os.getenv('VL_BASE_URL', "http://10.16.1.7:8088/v1"),
    timeout=360.0
)

client = OpenAI(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    base_url=os.getenv('DS_BASE_URL', "https://dashscope.aliyuncs.com/compatible-mode/v1")
)


# ================================
# 登录鉴权装饰器
# ================================
def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


# ================================
# 辅助函数
# ================================

# def allowed_file(filename: str) -> bool:
#     """检查文件扩展名是否允许上传"""
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def get_keyframe_urls(keyframes_dir: str) -> list:
    """
  获取关键帧的URL列表，构造相对于 static 目录的路径
  """
    image_urls = []
    relative_path = os.path.relpath(keyframes_dir, os.path.join(os.getcwd(), 'static'))
    for file in os.listdir(keyframes_dir):
        if file.lower().endswith(('.jpg', '.jpeg')):
            url = f'/static/{relative_path}/{file}'
            image_urls.append(url)
    return image_urls


def get_image_base64(image_path: str) -> str:
    """将图片转换为 base64 格式字符串"""
    with open(image_path, 'rb') as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def excel_prompt(file_path: str, sheet_name: str = '师幼空间指标'):
    """
  读取 Excel 表格中的提示信息（示例函数）
  """
    wb = load_workbook(file_path)
    ws = wb[sheet_name]
    return ws


def call_behavior_analysis(video_description: str, user_prompt: str) -> str:
    """
  调用百炼模型服务进行儿童行为分析
  根据视频描述和用户提示构建 prompt，并返回模型输出
  """
    ws = excel_prompt("/home/dut/video-analysis-test/师幼空间幼儿活动关键经验指标.xlsx")
    prompt = (
        "你是一名专业的幼儿行为分析师，擅长结合《3-6岁儿童学习与发展指南》观察和分析儿童的行为表现。\n"
        "# 任务目标\n"
        "请你从专业的角度，根据要求一步步思考，对视频中儿童的表现进行详细的评价和分析。\n\n"
        "# 输出要求\n"
        "1. 客观描述观察到的具体行为\n"
        "2. 分析这些行为反映的能力和特点\n"
        "3. 对儿童发展水平的专业评估,结合儿童的表现给出对应的不同水平的评估\n"
        "4. 提供适当的建议\n\n"
        "# 输入数据\n"
        "以下是视频的详细描述：\n"
        f"{video_description}\n\n"

        "# 输出格式\n"
        "请按照以下格式输出分析结果：\n"
        "## 观察到的主要行为\n"
        "列出关键行为表现\n\n"
        "## 分析评价\n"
        "固定开头：结合《3-6岁儿童学习与发展指南》五大领域下的各发展目标，对[幼儿姓名]在本次游戏中体现出的发展关键经验与发展水平分别进行如下分析评价：\n"
        "- 每个幼儿独立分析并评分，根据视频内容选择3-5个维度进行分析，按照《分析评价》的要求，各维度分析不少于150个中文字符长度\n\n"
        "## 教育建议\n"
        "- 按照《支持策略》的要求进行总体评价和建议，自然丰满，避免使用笼统或模板化的语言，而是根据观察到的具体行为进行深入分析\n\n"

        "分析评价：\n"
        "1. 根据视频内容对每个幼儿自动匹配3-5个最相关分析维度,对幼儿进行详细的评价分析和评分\n"
        "2. 分析和评分需严格基于视频中幼儿的具体表现，参考以下标准：\n"
        f"{ws}\n"
        "3. 评分要求：\n"
        "   - 根据视频内容自动匹配表格中3-5个最相关二级指标，每个指标须对应≥2个具体行为实例，采用1-5分制\n"
        "   - 示例匹配逻辑：建构游戏→建构技能；角色游戏→角色认知\n"
        "   - 需体现领域间差异，禁止出现全水平3或全水平5\n"
        "4. 对不同幼儿有尽可能详细的描述,针对不同幼儿进行评价分析，不少于150个中文字符长度\n"
        "5. 评价分析和评分标准必须严格使用以下二级指标名称，不要修改任何字符\n"
        "   - 游戏兴趣，情绪调控\n"
        "   - 角色认知，角色分配，角色表现，主题情节，材料认知与使用\n"
        "   - 建构主题，建构技能，材料认知，材料使用，记录表征，拼插技能\n"
        "   - 感受欣赏，美的表现力，材料认知，材料使用，问题解决，工具使用\n"
        "   - 观察能力，理解能力，解决问题，精细动作\n"
        "   - 倾听习惯，讲述能力，描述能力，阅读习惯，符号意识，前书写能力\n"
        "   - 数的认知，数的运算，量的感知，数量关系，几何形体，空间方位，空间视觉化，模式，分类，时间认知\n"
        "   - 观察能力，猜想假设，实验操作，信息采集与记录，分析思考，结果的表达交流\n"
        "   - 观察能力，种植与饲养，测量与记录，分析思考，交流与表达，认识动植物，爱护动植物\n"
        "   - 作品理解，主题情节，角色分配，角色认知和行为，材料选择与使用\n"
        "   - 探究能力，塑形能力，问题解决，材料选择与使用\n"
        "   - 材料收整，记录与表征，回顾能力，叙事能力，描述能力，倾听习惯\n"
        "   - 动作准确性，动作合拍性，动作动力性\n"
        "   - 走，跑，立定跳远，单脚跳，双脚连续跳，钻，爬，滚动与滚翻，脚踢球，拍篮球，骑行\n"
        "   - 平衡性，协调性，灵敏性，力量，耐力\n"
        "   - 穿脱衣物，清洁整理，饮食自理，时间管理\n"
        "   - 问候习惯，个人卫生，作息规律，安全意识，环保意识\n"
        "   - 社交兴趣，融入游戏，友好相处，遵守规则，合作倾向，处理矛盾，尊重他人，自我认同，诚实守信，履行职责，热爱集体\n"
        "   - 主动性，目的性，计划性，专注性，独立性，坚持性，反思性，创造性\n\n"
        "6. 严格按照格式示例输出内容\n\n"

        "# 分析评价输出格式示例\n"
        "结合《3-6岁儿童学习与发展指南》五大领域下的各发展目标，对笑笑、小罗在本次游戏中体现出的发展关键经验与发展水平分别进行如下分析评价：\n"
        "笑笑：\n"
        "1.精细动作——水平5\n"
        "笑笑是个追求完美的孩子，从包、捏、拧糖果的动作中可以看到，笑笑已经掌握了包和拧的动作技能，能够把糖果包得严严实实的，说明他的手部小肌肉运动很灵活。\n"
        "2.规则意识——水平5\n"
        "笑笑对于两个人定好的交换规则能愉快地遵守着。两个孩子高兴地体验游戏过程，并在这个过程中学会了协商、交换、轮流等交往技能。孩子们在游戏中自然获得的这些经验，将会对他们以后的交往行为产生正面的影响。\n"
        "3.处理矛盾——水平3\n"
        "大概是看到了教师和小罗比较有趣的互动，笑笑终于忍不住，也想主导“卖糖果”游戏了。值得高兴的是，笑笑没有向强势的小罗一味让步，而是勇敢地表达自己的想法。在遇到问题时，他也没有仗着自己身体、年龄上的优势选择用暴力去解决，而是尽可能与小罗进行沟通，这对于一个小班的孩子来说尤为难得。在三次争取失败后，他选择了向教师求助，说明他知道在必要时寻求别人的帮助。在笑笑向教师求助后，教师选择了适当介入。看得出，教师提出的问题引发了两个孩子的思考：笑笑开始啃咬手指，说明他虽然求助了，但对于能否顺利解决问题心里没底，比较焦虑。\n"
        " 4.主题情节——水平4\n"
        "在游戏过程中，笑笑能够在教师一句简单的提问——“是什么味道的”下,调动自己关于糖果的口味的原有经验，并开始想象自己包好的糖果的各种口味，游戏情节也因此变得有趣和复杂起来。\n\n"
        "小罗：\n"
        "1.精细动作——水平3\n"
        "从小罗包、捏、拧糖果的动作中可以看到，他包装的糖果总是不听话地掉出来，即便没有掉出来也露在糖纸的外面，说明他的精细动作相对来说较弱一些。\n"
        "2.创造性——水平3\n"
        "小罗在包完糖果后想出了卖糖果的游戏，说明他的创造力相对来说比较丰富。\n"
        "3.坚持性——水平5\n"
        "小罗年龄虽然比较小，但做事的坚持性很好，对于商量好的3分钟之后互换的规则，他在游戏中一直记在心里。\n"
        "4.数的认知——水平2\n"
        "小罗发现教师对糖果的价格不满意后马上进行调整，能够主动把糖果的价格从5元降到1元，说明他已经能够很好地分辨5以内数的大小。\n"
        "5.处理矛盾——水平3\n"
        "小罗在整个矛盾纠纷过程中，表现得很强势，也很固执，这可能与他的年龄特点有关系。他比笑笑小整整一年，他的身上还带着小班幼儿非常明显的“以自我为中心”的特点，不会主动考虑他人的感受，这也是很正常的，是可以理解的。在教师的引导下，原本比较强势的小罗能够主动出主意解决问题，而且把游戏的机会首先让给了笑笑。这也再次说明，游戏中的争执并不是因为孩子所谓的“自私”,而是由孩子的年龄特点导致的。只要教师引导得法，孩子们完全能够学会处理矛盾的技巧。\n\n"

        "教育建议：\n"
        "#结构要求：\n"
        "1. 总体评价：\n"
        "- 嵌入情境：当...时表现出...\n"
        "- 群体参照：相较于同龄幼儿...\n"
        "- 成长叙事：从最初...到如今...\n"
        "- 根据《分析评价》要求进行总体评价\n"
        "- 《分析评价》要求:\n"
        "- 分析评价的依据性:指对幼儿行为的分析评价都是依据于本次的观察记录。避免脱离观察记录本身“未记先评”、 “先入为主”、“无中生有”。\n"
        "- 分析评价的多元性:指分析评价会关注幼儿发展的多个领域、多个方面，全面的、多元的分析幼儿的行为表现。结合幼儿行为从多个领域、多个维度的关键发展指标进行条分缕析地分析。\n"
        "- 分析评价的深入性:对观察结果的分析评价不停留在泛泛的“领域”，能够深入到具体的领域发展目标、典型行为表现上。将幼儿的行为表现聚焦于幼儿某个领域的某个方面的某个发展目标上，进行具体、深入的分析。\n"
        "- 分析评价的发展性:对观察结果的分析是发展性的，能够比较准确地描绘出幼儿下一步发展的方向和目标。\n"
        "2. 具体策略：\n"
        "- 分3-5点，含分层材料、师幼互动、家园协同等维度 \n"
        "- 每点包含实施方式和理论依据\n"
        "- 根据《支持策略》要求进行支持策略分点分析，不要显示具体性等词语\n"
        "- 《支持策略》要求\n"
        "- 支持策略的具体性:后续教育策略都是围绕此次观察活动的具体的、可操作的教育建议。避免宽泛的、笼统的教育策略。要结合分析结果以及本次活动或观察对象的实际情况制定具体的支持策略。\n"
        "- 支持策略的发展性:提出的后续支持策略具有较强的发展性，能够准确基于幼儿下一步发展的方向和目标（最近发展区）提出教育建议。\n"
        "- 支持策略的关联性:观察记录中对幼儿行为的描述可以很好地对应对幼儿行为的分析，对幼儿行为的分析也可以很好地对应支持策略。\n\n"

        "教育建议输出示例：\n"
        "在最近的体育游戏中，孩子们在滚筒行走的活动中展现了令人惊喜的成长与进步。洋洋通过多次自主探索，成功学会了站在滚筒上行走，西西通过观察其他幼儿游戏受到启发，经过自己的努力，借助其他工具成功地站在了滚筒上，越来越勇敢、坚定。在体育游戏中，当孩子们遇到困难时我们总是想要过去扶一把，其实我们不妨再等一等，你会被他们的巨大潜能和坚持探索的强大意志力所感动。\n"
        "1.放手并相信孩子。\n"
        "当孩子遇到困难时老师不妨等一等，相信孩子巨大的潜能和学习能力。洋洋作为男生具有更强的冒险精神和探索能力，所以我全程没有介入他的游戏。当西西第一次尝试失败后我没有直接帮助，而是通过语言提示鼓励她继续尝试，不论她的尝试是否成功。当她有了新想法、借助了辅助材料时给予认可和鼓励，使幼儿在克服困难、体验成功的过程中获得自信。\n"
        "2.交流分享，共同提高。\n"
        "鼓励幼儿将游戏过程画下来，并分享他们的方法，讨论怎样才能更平稳地站上滚筒并向前走。学习他人的成功经验，提高自己的游戏能力。\n"
        "3.正确示范，分层练习。\n"
        "下一步可以为幼儿示范保持平衡的技巧和方法，如停下来张开手臂等。在练习滚筒上行走时，先练习借助辅助器械站上滚筒，然后自主平稳站上滚筒，再练习慢速在滚筒上向前行走一段距离，最后达到在滚筒上自如行走。分层练习，循序渐进。\n\n"

        "# 强制验证\n"
        "执行以下检查（任一不通过立即报错）：\n"
        "1. 统计出现'幼儿'/'孩子'等关键词次数 ≥3次\n"
        "2. 至少描述2个不同幼儿的行为\n"
        "3. 包含具体动作描述（如搭建/奔跑/绘画）\n\n"
        "# 错误处理\n"
        "未通过验证时返回：[ERROR] 未检测到有效幼儿活动\n"
        "# 输出格式\n"
        "直接输出幼儿观察分析，不要输出其他信息。\n"
    )
    completion = client.chat.completions.create(
        model="qwen-max-2025-01-25",
        temperature=0.0,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return completion.model_dump_json()


def call_multimodal_conversation(keyframes: list) -> str:
    """
  调用百炼视觉模型服务，对关键帧图片序列进行视觉分析
  参数 keyframes 为图片 URL 列表，构造消息时依次附加图片信息
  """
    base_prompt = (
        "# 角色\n"
        "你是一位全球顶尖的幼儿行为观察学者，具备细致观察力和敏锐的逻辑分析能力，你擅长用温暖生动的语言描述孩子们的行为，同时保持教育观察的专业性，客观精准记录和描述每个画面中的细微差别。\n\n"
        "# 核心指令\n"
        "严格基于输入的关键帧图像序列进行视觉分析，输出幼儿活动观察报告。\n"
        "绝对禁止任何推测/想象/补全\n"
        # "严格遵循：证据锚定→逻辑链构建→反事实检验的工作流，一步步思考还原视频内容\n"
        # "若检测到非幼儿园场景或无3-6岁幼儿立即终止并报错。\n\n"
        "# 任务描述\n"
        "给你一个视频片段的多张关键帧图片和文字描述（各观察对象的特征，语言描写或者其他相关的信息），请按照要求输出《幼儿观察记录》，捕捉孩子们可爱的原话和有趣的小动作，除此之外不需要任何解释和回复。\n"
        "- 幼儿玩游戏的视频，可能对应一些常见幼儿园游戏：滚筒游戏｜建构游戏（积木/轨道）｜角色游戏（娃娃家/小医院）｜美工创造（黏土/绘画）｜沙水游戏｜户外运动（平衡木/骑行/球类）｜科学探究（种植/测量）\n"
        "1.身体运动类：滚轮胎（双臂协调）、跳圈圈（双脚跳跃）、爬隧道（空间感知）、丢沙包（投掷能力）、走平衡（身体控制）\n"
        "2.动手操作类：串珠子（手眼协调）、捏橡皮泥（手指力量）、折纸飞机（步骤记忆）、扣纽扣（精细动作）、拼拼图（形状匹配）\n"
        "3.角色体验类：过家家（家庭场景）、小医生（医疗道具）、超市购物（货币交易）、建筑工地（工具模仿）、动物模仿（肢体表达）\n"
        "4.集体互动类：老狼几点了（追逐反应）、丢手绢（轮流规则）、传小球（物品传递）、 红绿灯（指令执行）\n"
        "5.感官探索类：摸箱子（触觉辨认）、听声音（听觉辨别）、闻味道（嗅觉训练）、找颜色（视觉搜索）、尝味道（味觉体验）\n"
        "6.建构创造类：搭积木（空间建构）、堆沙堡（立体造型）、拼乐高（机械组合）、摆石子（图案排列）\n"
        "7.自然探索类：捡树叶（自然观察）、浇花草（责任培养）、捉影子（光影认知）、滚山坡（重力体验）、玩水坑（液体特性）\n"
        "- 输出每张图片的画面信息，包括人物、物体、动作、文字、字幕、一句话总结等。\n"
        "- 把每张图片的信息串联起来，使用时间连接词（随后/同时/接着）衔接不同帧的关联动作，生成视频的详细概述，还原该片段的剧情，保持专业观察的客观性，但不要冷冰冰的。\n\n"
        
        # "任务流程\n"
        # "1. 原子事实提取\n"
        # "a. 幼儿数量确认：统计可见幼儿人数，记录服饰特征（如：穿蓝色条纹衫的男孩）\n"
        # "b. 动作分解：对每个幼儿执行『身体部位-物体-空间关系』三元组分析\n"
        # "示例：\n"
        # "   - 左手：五指张开握住积木底部（指节弯曲角度＞30°）\n"
        # "   - 右脚：前脚掌接触地面，脚跟离地3cm\n"
        # "c. 物体状态记录：量化关键参数（如沙堆高度≈幼儿坐高的2/3）\n\n"
        # "2. 时空逻辑链构建\n"
        # "使用时序推理模板：\n"
        # "当[前帧状态]时，通过[当前帧变化]，可推导[动作类型]（置信度）\n"
        # "示例：\n"
        # "- 前帧：积木塔高度=25cm（基准线）\n"
        # "- 当前帧：积木塔高度=28cm + 右手处于释放动作\n"
        # "- 推导：执行了『叠加』动作（置信度90%）\n\n"
        # "3. 反事实校验\n"
        # "对每个推理节点应用3F检验法：\n"
        # "a. Frame-Check：是否在连续两帧以上出现相关证据？\n"
        # "b. Force-Check：该动作是否符合3-6岁儿童肌肉力量水平？\n"
        # "c. Focus-Check：注意力焦点是否持续超过2秒（通过瞳孔方向与头部朝向计算）？\n\n"
        # "错误示例：'幼儿钻进滚筒'（错误原因：未观察到二分之一以上身体被滚筒遮挡）\n"
        # "正确示例：'幼儿站在滚筒上'（正确依据：双腿可见于滚筒外部）\n"
        
        "# 限制\n"
        "- 分析范围严格限定于提供的视频子片段，不涉及视频之外的任何推测或背景信息。\n"
        "- 总结时需严格依据视频内容，不可添加个人臆测或创意性内容。不要出现教师的意识以及心理活动，过程实录最后不要出现总结性或者评价性的语句\n"
        "- 视频可能拍摄于幼儿园的某个区域，包括：建构区 、美工区 、益智区、 表演区、 科学区、 图书区、 娃娃家、 自然角、数学区、沙水区、户外运动区等，请给出最可能的地点\n"
        "- 保持对所有视频元素（尤其是文字和字幕）的高保真还原，避免信息遗漏或误解。\n"
        "- 每个动词必须对应至少两个视觉证据（如『揉捏』需同时观察到：指关节弯曲+黏土形变）\n"
        # "- 首要聚焦幼儿直接互动物品（与幼儿肢体接触或视线聚焦2秒以上的物体）\n"
        # "- 场景物品的判断要符合物理属性和日常常识，比如滑梯的高度>幼儿身高\n"
        "- 根据关键帧图像，用温暖专业的语言写出观察记录，不要使用『该幼儿』这样的生硬称呼\n"
        "- 禁止出现对话，禁止猜测幼儿间的对话\n"
        "- 严禁出现xx说：这种对话类句式\n\n"
        "# 输出格式\n"
        "直接按照任务目标里即可，先输出每张图片的描述，再串联起来输出整个视频片段的剧情，不可添加视频中未出现的内容，不少于500个中文汉字文本长度。\n"
        "按时间顺序呈现每张图像中：\n"
        "- 主要角色（描述特征）及其正在进行的具体动作\n"
        "- 关键物体状态（位置/形态/使用方式）\n"
        "- 环境文字/标识内容（精确到字符）\n\n"
        "用2-4个自然段描述：\n"
        "1. 起始场景：时间/地点/初始人物配置\n"
        "2. 过程演进：关键交互动作与物体状态变化\n"
        "3. 阶段成果：当前片段结束时呈现的状态\n\n"

        "# 输出格式示例\n"
        "- 区域游戏开始了，小明来到美工区开始制作“棒棒糖”，她拿着一盒白色的超轻粘土，从里面取出一小块黏土，单手揉捏了一下随后又用两只小手合并揉了一下，便开始往一根木根的顶端粘贴，粘上去后她来回按压，使黏土和木根的粘合更牢固一些。粘贴好之后她将“白色棒棒糖”并排放在另一跟已经做好的“棒棒糖”旁边，准备继续制作下一个。\n"
        "- 她拿起黏土准备再取出一些，忽然发现没有木棍了，于是她起身从材料架上又拿来一根木棍。她继续左手端着黏土盒，右手多次从里面挖出黏土，并单手里来回揉捏使黏土变圆润。随后，她将揉好的白色黏土开始往木棍的顶端粘贴。单面粘贴牢固后，她将黏土向后拨，使其整个包围在木棍头的位置上，做好后她又将作品并排摆上刚才的作品旁边。随后，她拿起超轻黏土盒准备继续进行“棒棒糖”制作游戏......\n"
        
        # "# 强制检测规则\n"
        # "若画面中未出现3-6岁幼儿或幼儿园立即报错\n"
        # "# 错误格式\n"
        # "发现上述情况时直接返回：[ERROR] 未检测到幼儿活动\n\n"
    )
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": base_prompt}
        ]
    }]
    for url in keyframes:
        messages[0]['content'].append({
            "type": "image_url",
            "image_url": {"url": url}
        })
    response = vl_client.chat.completions.create(
        # model="Qwen2-5-VL-32B-Instruct",
        model="InternVL3",
        messages=messages,
        temperature=0.0,
        top_p=1,
        max_tokens=4096
    )
    return response.model_dump_json()


def call_text_completions(video_analysis_text: str) -> str:
    """
  调用文本模型服务，根据视觉模型返回的文本生成最终视频描述
  """
    prompt = (
        "# 角色\n"
        "你是一个经验丰富的幼儿园老师，擅长修改幼儿观察记录。用温暖、生动、像讲故事一样的语言修改幼儿观察记录。同时你也是一位作家，文风温和准确没有过多的比喻\n\n"
        "# 核心指令\n"
        "基于视频关键帧分析生成符合《幼儿园观察记录》标准的客观叙述，若检测到非3-6岁幼儿活动立即终止并报错。\n\n"
        "# 任务目标\n"
        "请你结合输入数据串联、还原出整个幼儿活动的详细情况。\n\n"
        "# 限制\n"
        "1. 如出现语法上错误，或逻辑不通，请直接修改\n"
        "2. 在描述中，如果包含台词，可能会出现说话者与其所说内容不匹配的情况。因此，必须根据剧情的进展，准确判断每段台词的真实说话者\n"
        "3. 如果记录中无台词，请根据视频音频文字为其匹配台词。若未提供音频，不要杜撰台词。\n"
        "4. 修改后的故事请适当保留对人物、动作、区域的描写\n"
        "5. 文字由多次模型调用生成，每段描述图片序号都从1开始，请注意合并使其更具逻辑性，但要避免主观描写\n"
        "6. 结合人物外观特点，如果有外观相近的人物是同一个角色。因此，需要将不同描述中的人物角色统一，不要用孩子、幼儿等词语统一代指，禁止使用'该幼儿'、'女孩A'这样的生硬称呼。\n"
        "7. 活动实录中只要白描描写，不要出现评价性或者总结性的内容，不要出现模糊词语（好像、似乎、可能、仿佛）\n"
        "8. 保持专业观察的客观性，但不要冷冰冰的，可以适当使用口语化表达，注意捕捉孩子们可爱的细节和小表情，记录对话时要保留孩子说话时稚嫩的语气\n"
        "9. 禁止猜测幼儿间的对话\n"
        "10. 禁止出现-符号\n"
        "11. 描述不要多于三段\n\n"
        "# 输入数据\n"
        "## 资料一：幼儿观察记录\n"
        f"{video_analysis_text}\n\n"
        "- 《过程实录》要求\n"
        "- 观察目的与观察内容紧密相连，即便没有明确的观察目的，也能从观察内容中看到教师观察的重点，避免“流水账”现象的出现。要注重：客观性、完整性、细致性三个重点来描写\n"
        "- 记录的是事实，而不是观点。详细记录幼儿的语言、神态、动作、表情等。客观描述幼儿的行为表现，很少使用主观词汇或对幼儿的想法或意愿进行主观猜测。\n"
        "- 完整记录幼儿行为发生的前因、过程和结果。前因：幼儿行为发生的前因和背景（环境、人等） 是什么？过程:幼儿的行为表现，包括幼儿说了什么、做了什么？结果: 幼儿行为的结果，包括幼儿的感受和收获、 周围人的反应是什么？\n"
        "- 对观察重点作细致、生动的描写，非重点的内容简略描述 。避免大概、笼统地描述幼儿的关键行为表现。围绕观察重点进行拆解，对相关的关键行为进行详细的观察和记录。不要出现以下词语：“好像、可能、似乎、仿佛”\n"
        "- 不要大量使用”显示出“等词语，例如：小杰让游戏板上的磁珠分布再次发生变化，他在不断尝试新的路径或组合\n"
        "- 避免语言表达机械化，模仿人类（幼儿园老师）的写作风格，具备描述自然性与表达丰富度\n\n"
        "# 输出格式\n"
        "根据《过程实录》要求直接输出修改好的幼儿观察记录，不要输出其他信息，不要出现评价性或者总结性的内容。\n"
        "# 改写示例\n"
        "原内容\n"
        "- 女孩A将黏土粘贴到木棍上\n"
        "优化后\n"
        "- 小明从盒子里面取出一小块黏土，单手揉捏了一下随后又用两只小手合并揉了一下，往一根木根的顶端粘贴，粘上去后她来回按压，使黏土和木根的粘合更牢固一些。\n\n"

        "# 输出格式示例\n"
        "- 观察对象：穿着白色带有花卉图案上衣的幼儿（暂称小明）\n"
        "- 过程实录：\n"
        "- 区域游戏开始了，小明来到美工区开始制作“棒棒糖”，她拿着一盒白色的超轻粘土，从里面取出一小块黏土，单手揉捏了一下随后又用两只小手合并揉了一下，便开始往一根木根的顶端粘贴，粘上去后她来回按压，使黏土和木根的粘合更牢固一些。粘贴好之后她将“白色棒棒糖”并排放在另一跟已经做好的“棒棒糖”旁边，准备继续制作下一个。\n"
        "- 她拿起黏土准备再取出一些，忽然发现没有木棍了，于是她起身从材料架上又拿来一根木棍。她继续左手端着黏土盒，右手多次从里面挖出黏土，并单手里来回揉捏使黏土变圆润。随后，她将揉好的白色黏土开始往木棍的顶端粘贴。单面粘贴牢固后，她将黏土向后拨，使其整个包围在木棍头的位置上，做好后她又将作品并排摆上刚才的作品旁边。随后，她拿起超轻黏土盒准备继续进行“棒棒糖”制作游戏......\n\n"
    )
    completion = client.chat.completions.create(
        model="qwen-max-2025-01-25",
        messages=[{'role': 'user', 'content': prompt}],
    )
    return completion.model_dump_json()


def cleanup_old_files():
    """
  定时清理超过指定时间（此处为 600 秒，可调整为 86400 秒，即24小时）的关键帧目录
  """
    current_time = time.time()
    for session_dir in os.listdir(app.config['KEYFRAMES_FOLDER']):
        dir_path = os.path.join(app.config['KEYFRAMES_FOLDER'], session_dir)
        if os.path.isdir(dir_path):
            dir_time = os.path.getctime(dir_path)
            if current_time - dir_time > 600:
                try:
                    shutil.rmtree(dir_path, ignore_errors=True)
                    logger.info(f"已清理旧目录：{dir_path}")
                except Exception as e:
                    logger.error(f"清理目录 {dir_path} 失败：{str(e)}")


# ================================
# 关键帧提取函数（保留现有实现）
# ================================
def extract_key_frames(filename: str, video_path: str, output_folder: str,
                       start_time: float = 0, end_time: float = None,
                       frames_per_second: int = 10, similarity_threshold: int = 30) -> None:
    """
  从视频中提取关键帧并保存到指定目录
  支持场景检测，如未检测到场景变化则采用均匀采样方式
  """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    video_manager = VideoManager([video_path])
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=similarity_threshold))

    try:
        video_manager.set_downscale_factor()
        video_manager.start()
        scene_manager.detect_scenes(frame_source=video_manager)
        scene_list = scene_manager.get_scene_list()
        logger.info(f"检测到 {len(scene_list)} 个场景")

        frame_records = []
        if len(scene_list) == 0:
            logger.info("未检测到场景变化，按均匀时间间隔采样帧")
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise RuntimeError("无法打开视频文件")
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps
            interval = duration / 30
            time_points = [i * interval for i in range(30)]
            for t in time_points:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ret, frame = cap.read()
                if ret:
                    frame_records.append({
                        "timestamp": t,
                        "frame_num": cap.get(cv2.CAP_PROP_POS_FRAMES),
                        "scene_num": 0,
                        "frame": frame
                    })
            cap.release()
        else:
            if len(scene_list) > 40:
                step = len(scene_list) / 40
                scene_list = [scene_list[int(i * step)] for i in range(40)]
                logger.info("场景数量超过40，均匀抽样至40个场景")
                frames_per_scene = 1
            else:
                scene_count = len(scene_list)
                if scene_count == 1:
                    frames_per_scene = 30
                elif 2 <= scene_count <= 4:
                    frames_per_scene = 10
                elif 5 <= scene_count <= 7:
                    frames_per_scene = 5
                elif 8 <= scene_count <= 10:
                    frames_per_scene = 4
                elif 10 < scene_count < 15:
                    frames_per_scene = 3
                elif 15 <= scene_count <= 20:
                    frames_per_scene = 2
                else:
                    frames_per_scene = 1
                logger.info(f"检测到 {scene_count} 个场景，每个场景采样 {frames_per_scene} 帧")
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise RuntimeError("无法打开视频文件")
            for scene_num, (start, end) in enumerate(scene_list, 1):
                start_sec = start.get_seconds()
                end_sec = end.get_seconds()
                time_points = np.linspace(start_sec, end_sec, frames_per_scene + 2)[1:-1]
                for t in time_points:
                    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                    ret, frame = cap.read()
                    if ret:
                        frame_records.append({
                            "timestamp": t,
                            "frame_num": cap.get(cv2.CAP_PROP_POS_FRAMES),
                            "scene_num": scene_num,
                            "frame": frame
                        })
            cap.release()

        frame_records.sort(key=lambda x: x["timestamp"])
        for idx, record in enumerate(frame_records, 1):
            output_path = os.path.join(
                output_folder,
                f"{filename}_scene_{int(record['scene_num']):03d}_"
                f"{record['timestamp']:.2f}s_{int(record['frame_num']):05d}.jpg"
            )
            cv2.imwrite(output_path, record["frame"])
            logger.info(f"已保存关键帧：{output_path}")
    finally:
        video_manager.release()


# ================================
# 路由定义
# ================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录页面"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'dut' and password == 'dut123456':
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')


@app.route('/logout')
def logout():
    """退出登录"""
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route('/', methods=['GET'])
@require_login
def index():
    """首页显示前端页面"""
    return render_template('index1.html')


@app.route('/api/upload', methods=['POST'])
@require_login
def handle_upload():
    """
  视频上传接口：
    - 校验文件格式
    - 保存至 UPLOAD_FOLDER
    - 创建唯一 keyframe 目录，调用关键帧提取
    - 检查关键帧数量范围
    - 删除原视频文件并返回关键帧 URL 列表
  """
    if 'file' not in request.files:
        logger.error("上传请求中未包含文件字段")
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        logger.error("未选择文件")
        return jsonify({"error": "No selected file"}), 400
    # if not (file and allowed_file(file.filename)):
    #     logger.error("文件类型不允许")
    #     return jsonify({"error": "File type not allowed"}), 409

    try:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        logger.info(f"文件保存至 {file_path}")

        import uuid
        session_id = str(uuid.uuid4())
        output_folder = os.path.join(app.config['KEYFRAMES_FOLDER'], session_id)
        os.makedirs(output_folder, exist_ok=True)

        # extract_key_frames(filename, file_path, output_folder, start_time=0, end_time=None, frames_per_second=10,
        #                    similarity_threshold=30)
        from frames_v2 import extract_frames_cover_whole_video
        extract_frames_cover_whole_video(
            video_path=file_path,          # ← 修改为你的视频路径
            output_dir=output_folder,             # ← 输出图像目录
            max_frames=36,
            output_size=(512, 512)
        )
        
        image_urls = get_keyframe_urls(output_folder)
        logger.info(f"提取到 {len(image_urls)} 个关键帧")

        if len(image_urls) < 4 or len(image_urls) > 512:
            logger.error("关键帧数量不符合要求")
            return jsonify({"error": "The number of keyframes must be between 4 and 512."}), 400

        os.remove(file_path)
        logger.info("上传视频文件已删除")
        return jsonify({'code': 200, 'data': {'keyframes': image_urls}})
    except Exception as e:
        logger.exception("视频上传处理异常")
        return jsonify({"error": str(e)}), 500


@app.route('/api/vision-analysis', methods=['POST'])
@require_login
def handle_vision_analysis():
    """
  视觉分析接口：
    1. 接收 keyframes（图片 URL 列表）与 prompt
    2. 并行处理图片：将 URL 转为本地路径并转换为 base64 字符串
    3. 分批并行调用视觉模型接口（每批 30 张），合并返回文本
    4. 调用文本模型生成最终视频描述
  """
    try:
        data = request.json
        keyframes = data.get('keyframes')
        prompt = data.get('prompt', '')

        if not keyframes or not isinstance(keyframes, list):
            logger.error("缺少关键帧数据")
            return jsonify({'error': '缺少关键帧数据'}), 400

        # 为避免字符串排序问题，按文件名中的数字排序
        keyframes = sorted(keyframes, key=lambda x: int(x.split('_')[-1].split('.')[0]))

        def process_image(url: str) -> str:
            """单个图片处理：从 URL 得到本地路径，转换为 base64"""
            try:
                parts = url.split('/static/')
                if len(parts) == 2:
                    relative_path = parts[1]
                    local_path = os.path.normpath(os.path.join('static', relative_path))
                    if os.path.exists(local_path):
                        logger.info(f"处理图片: {local_path}")
                        image_b64 = get_image_base64(local_path)
                        return f"data:image/jpeg;base64,{image_b64}"
                    else:
                        logger.warning(f"文件不存在: {local_path}")
                else:
                    logger.warning(f"URL 格式异常: {url}")
            except Exception as ex:
                logger.error(f"处理图片 {url} 异常：{str(ex)}")
            return None

        # 并行转换图片为 base64
        with ThreadPoolExecutor() as executor:
            base64_images = list(executor.map(process_image, keyframes))
        # 过滤转换失败的结果
        base64_images = [img for img in base64_images if img is not None]
        if not base64_images:
            logger.error("未能转换任何图片")
            return jsonify({'code': 400, 'data': '无法处理图片文件'}), 400

        batch_size = 10
        # 将图片分批
        batches = [base64_images[i:i + batch_size] for i in range(0, len(base64_images), batch_size)]
        # 并行调用视觉模型，每个批次调用保持顺序
        with ThreadPoolExecutor() as executor:
            responses = list(executor.map(call_multimodal_conversation, batches))
        results = []
        for response_raw in responses:
            response = json.loads(response_raw)
            if 'error' in response:
                logger.error(f"视觉模型错误: {response['error']['message']}")
                return jsonify({'code': 400, 'data': response['error']['message']})
            results.append(response['choices'][0]['message']['content'])

        video_analysis_text = "".join(results)
        data_raw = call_text_completions(video_analysis_text)
        final_description = json.loads(data_raw)['choices'][0]['message']['content']

        return jsonify({
            'code': 200,
            'data': {
                'description': final_description
            }
        })
    except Exception as e:
        logger.exception("视觉分析接口异常")
        return jsonify({'error': str(e)}), 500


@app.route('/api/behavior-analysis', methods=['POST'])
@require_login
def handle_behavior_analysis():
    """
  行为分析接口：
    - 接收 description 与 prompt
    - 调用行为分析模型生成详细报告
  """
    try:
        data = request.json
        description = data.get('description')
        prompt = data.get('prompt', '')
        if not description:
            logger.error("缺少视频描述数据")
            return jsonify({'error': '缺少视频描述数据'}), 400

        behavior_analysis_result = call_behavior_analysis(description, prompt)
        parsed_result = json.loads(behavior_analysis_result)
        analysis_text = parsed_result['choices'][0]['message']['content']

        return jsonify({
            'code': 200,
            'data': {
                'description': description,
                'analysis': analysis_text
            }
        })
    except Exception as e:
        logger.exception("行为分析接口异常")
        return jsonify({'error': str(e)}), 500


# ================================
# 定时清理任务（启动时清理旧文件）
# ================================
# @app.before_first_request
# def init_cleanup():
#     cleanup_old_files()


# ================================
# 程序入口
# ================================
if __name__ == "__main__":
    cleanup_old_files()
    # 建议生产环境使用 Gunicorn 或 uWSGI 部署
    app.run(host="0.0.0.0", port=8081, debug=False)
