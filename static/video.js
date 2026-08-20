document.addEventListener('DOMContentLoaded', function() {
    const root = document.getElementById('root');
    
    // 创建主容器
    const container = document.createElement('div');
    container.className = 'container';
    
    // 创建上传区域
    const uploadSection = document.createElement('div');
    uploadSection.className = 'upload-section';
    uploadSection.innerHTML = `
        <h2>上传视频</h2>
        <p>支持的格式: MP4</p>
        <input type="file" id="fileInput" accept=".mp4" style="display: none">
        <button class="upload-button" onclick="document.getElementById('fileInput').click()">选择文件</button>
        <p>或将文件拖放到此处</p>
    `;
    
    // 创建状态消息区域
    const statusMessage = document.createElement('div');
    statusMessage.className = 'status-message';
    statusMessage.style.display = 'none';
    
    // 创建进度显示区域
    const progressContainer = document.createElement('div');
    progressContainer.className = 'progress-container';
    progressContainer.innerHTML = `
        <div class="progress-step" data-step="extract">1. 提取视频关键帧 （完成后请点击视觉模型分析视频按钮）</div>
        <div class="progress-step" data-step="encode">2. 处理图片数据</div>
        <div class="progress-step" data-step="vision">3. 视觉模型分析 （耗时很长，请耐心等待）使用模型：Qwen2.5-VL-32b</div>
        <div class="progress-step" data-step="behavior">4. 儿童行为分析（点击儿童行为分析按钮） </div>
    `;
    
    // 创建关键帧容器（隐藏）
    const keyframesContainer = document.createElement('div');
    keyframesContainer.className = 'keyframes-container';
    
    // 创建结果显示区域
    const resultSection = document.createElement('div');
    resultSection.className = 'result-section';
    resultSection.style.display = 'none';
    resultSection.innerHTML = `
        <h3>分析控制</h3>
        <div class="analysis-controls">
        <button class="analyze-button vision-analysis">视觉模型分析</button>
        <button class="analyze-button behavior-analysis" style="display:none;margin-left:10px">儿童行为分析</button>
        </div>
        <h3>行为分析提示词</h3>
        <textarea class="prompt-input">        
        # 角色\n
        你是一名专业的幼儿行为分析师，擅长观察和分析儿童的行为表现。\n\n
        # 任务目标\n
        请你从专业的角度，对视频中儿童的表现进行详细的评价和分析。\n\n
        # 分析维度\n
//        1. 社交互动能力：与他人的交流、合作、分享等行为\n
//        2. 情绪表现：情绪的类型、强度、调节能力\n
//        3. 认知能力：理解力、学习能力、创造力、专注度等\n
//        4. 语言表达：语言使用、表达清晰度、词汇量等\n
//        5. 行为特征：活动量、自主性、规则意识等\n
//        6. 兴趣爱好：对特定活动或事物的偏好\n\n
        1.兴趣状态：游戏兴趣和情绪调控\n
        2.角色游戏：角色认知，角色分配，角色表现，主题情节，材料认知与使用\n
        3.建构游戏：建构主题，建构技能，材料认知，材料使用，记录表征，拼插技能\n
        4.美工创造：感受欣赏，美的表现力，材料认知，材料使用，问题解决，工具使用\n
        5.益智游戏：观察能力，理解能力，解决问题，精细动作\n
        6.图书阅读：倾听习惯，讲述能力，描述能力，阅读习惯，符号意识，前书写能力\n
        7.数学认知：数的认知，数的运算，量的感知，数量关系，几何形体，空间方位，空间视觉化，模式，分类，时间认知\n
        8.科学探究：观察能力，猜想假设，实验操作，信息采集与记录，分析思考，结果的表达交流\n
        9.自然探究：观察能力，种植与饲养，测量与记录，分析思考，交流与表达，认识动植物，爱护动植物\n
        10.表演游戏：作品理解，主题情节，角色分配，角色认知和行为，材料选择与使用\n
        11.沙水游戏：探究能力，塑形能力，问题解决，材料选择与使用\n
        12.回顾分享：材料收整，记录与表征，回顾能力，叙事能力，描述能力，倾听习惯\n
        13.操节运动：动作准确性，动作合拍性，动作动力性\n
        14.动作技能：走，跑，立定跳远，单脚跳，双脚连续跳，钻，爬，滚动与滚翻，脚踢球，拍篮球，骑行\n
        15.运动素质：平衡性，协调性，灵敏性，力量，耐力\n
        16.自理能力：穿脱衣物，清洁整理，饮食自理，时间管理\n
        17.生活习惯：问候习惯，个人卫生，作息规律，安全意识，环保意识\n
        18.社会交往：社交兴趣，融入游戏，友好相处，遵守规则，合作倾向，处理矛盾，尊重他人，自我认同，诚实守信，履行职责，热爱集体\n
        19.学习品质：主动性，目的性，计划性，专注性，独立性，坚持性，反思性，创造性\n\n

        # 输出要求\n
        1. 客观描述观察到的具体行为\n
        2. 分析这些行为反映的能力和特点\n
        3. 对儿童发展水平的专业评估,结合儿童的表现给出对应的不同水平的评估\n
        4. 如有需要，可以提供适当的建议\n\n
        # 输出格式\n
        请按照以下格式输出分析结果：\n
        ## 观察到的主要行为\n
        （列出关键行为表现）\n\n
        ## 分析评价\n
        （选择六个维度进行分析，按照《分析评价》的要求）\n\n
        ## 五维评分\n
        （根据视频内容，选择五项最相关的二级指标评分）\n\n
        ## 支持策略\n
        （按照《支持策略》的要求）\n\n
        ## 发展评估\n
        （总体评价和建议，自然丰满，避免使用笼统或模板化的语言，而是根据观察到的具体行为进行深入分析）\n</textarea>
        
        <div class="analysis-result"></div>
    `;
    
    // 添加所有元素到容器
    container.appendChild(uploadSection);
    container.appendChild(statusMessage);
    container.appendChild(progressContainer);
    container.appendChild(keyframesContainer);
    container.appendChild(resultSection);
    root.appendChild(container);
    
    // 处理文件拖放
    setupDragAndDrop(uploadSection);
    
    // 处理文件选择
    document.getElementById('fileInput').addEventListener('change', handleFileSelect);
    
    // 处理视觉分析按钮点击
    const analyzeButton = resultSection.querySelector('.vision-analysis');
    analyzeButton.addEventListener('click', handleVisionAnalysis);

    // 处理行为分析按钮点击
    const behaviorButton = resultSection.querySelector('.behavior-analysis');
    behaviorButton.addEventListener('click', handleBehaviorAnalysis);

});
function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, tag => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        "'": '&#39;',
        '"': '&quot;'
    }[tag]));
}

function setupDragAndDrop(uploadSection) {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        uploadSection.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        uploadSection.addEventListener(eventName, () => {
            uploadSection.classList.add('drag-over');
        });
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        uploadSection.addEventListener(eventName, () => {
            uploadSection.classList.remove('drag-over');
        });
    });
    
    uploadSection.addEventListener('drop', (e) => {
        const file = e.dataTransfer.files[0];
        if (file && file.type === 'video/mp4') {
            handleFileUpload(file);
        } else {
            alert('请上传 MP4 格式的视频文件');
        }
    });
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        handleFileUpload(file);
    }
}

async function handleFileUpload(file) {
    const formData = new FormData();
    formData.append('file', file);
    const progressContainer = document.querySelector('.progress-container');
    const statusMessage = document.querySelector('.status-message');

    try {
        // 显示进度条并更新状态
        progressContainer.style.display = 'block';
        updateProgress('extract', 'active');
        
        statusMessage.style.display = 'block';
        statusMessage.textContent = '正在处理视频，请稍候...';
        
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.code === 200) {
            updateProgress('extract', 'completed');
            statusMessage.textContent = `成功提取 ${result.data.keyframes.length} 个关键帧`;
            // 隐藏显示关键帧，但保存数据
            displayKeyframes(result.data.keyframes);
            document.querySelector('.result-section').style.display = 'block';
        } else {
            statusMessage.textContent = '上传失败：' + (result.error || '未知错误');
            if (result.error.includes("The number of keyframes must be between 4 and 512")) {
                alert('提取的关键帧数量不符合要求，请选择其他视频。');
            }
            resetProgress();
        }
    } catch (error) {
        statusMessage.textContent = '上传出错：' + error.message;
        //console.log(error.messageS);
        resetProgress();
    }
}

function displayKeyframes(keyframes) {
    const container = document.querySelector('.keyframes-container');
    container.innerHTML = '';
    
    keyframes.forEach(url => {
        const img = document.createElement('img');
        img.src = url;
        img.className = 'keyframe-image';
        container.appendChild(img);
    });
}

async function handleVisionAnalysis() {
    const keyframeImages = document.querySelectorAll('.keyframe-image');
    const statusMessage = document.querySelector('.status-message');
    const progressContainer = document.querySelector('.progress-container');
    const resultSection = document.querySelector('.result-section');
    
    if (keyframeImages.length === 0) {
        alert('请先上传视频');
        return;
    }

    // 创建终止控制器和超时设置
    const controller = new AbortController();
    const timeoutDuration = 1800 * 1000; // 1800秒 = 30分钟
    const timeoutId = setTimeout(() => {
        controller.abort();
        statusMessage.textContent = '请求超时，请重试';
        resetProgress();
    }, timeoutDuration); 

    try {
        // 获取用户选择的模型
        // const modelSelect = document.getElementById('modelSelect');
        // const selectedModel = modelSelect.value;

        // 1. 处理图片数据
        updateProgress('encode', 'active');
        statusMessage.textContent = '正在处理图片数据 (0/' + keyframeImages.length + ')';
        
        const keyframes = [];
        let processedCount = 0;
        
        for (const img of keyframeImages) {
            const url = new URL(img.src);
            keyframes.push(url.pathname);
            processedCount++;
            statusMessage.textContent = `正在处理图片数据 (${processedCount}/${keyframeImages.length})`;
            await new Promise(resolve => setTimeout(resolve, 10));
        }
        
        updateProgress('encode', 'completed');
        
        // 2. 开始视觉分析
        updateProgress('vision', 'active');
        statusMessage.textContent = `开始调用视觉模型分析 ${keyframes.length} 张图片...`;
        
        const prompt = document.querySelector('.prompt-input').value;
    
        const response = await fetch('/api/vision-analysis', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                keyframes,
                prompt
                // model: selectedModel  // 传递用户选择的模型
            }),
            signal: controller.signal //绑定终止信号
        });

        clearTimeout(timeoutId); //清除超时计时器

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.code === 200) {
            updateProgress('vision', 'completed');
            statusMessage.textContent = '视觉模型分析完成';
            
            // 显示行为分析按钮
            document.querySelector('.behavior-analysis').style.display = 'inline-block';
            // // 4. 生成描述
            // updateProgress('generate-desc', 'active');
            // statusMessage.textContent = '正在生成视频描述...';
            // await new Promise(resolve => setTimeout(resolve, 1000)); // 给用户一个视觉反馈的时间
            // updateProgress('generate-desc', 'completed');
            
            // // 5. 行为分析
            // updateProgress('analyze-behavior', 'active');
            // statusMessage.textContent = '正在进行儿童行为分析...';
            // await new Promise(resolve => setTimeout(resolve, 1000)); // 给用户一个视觉反馈的时间
            // updateProgress('analyze-behavior', 'completed');
            
            // updateProgress('analyze', 'completed');
            // updateProgress('generate', 'completed');
            // statusMessage.textContent = '分析完成！';
            

            const resultDiv = document.querySelector('.analysis-result');
            resultDiv.innerHTML = `
                <div class="result-section-title">视频描述</div>
                <pre class="description">${escapeHTML(result.data.description)}</pre>
                <div class="result-section-title">儿童行为分析</div>
                <div class="analysis"></div>
            `;
        } else {
            statusMessage.textContent = '分析失败：' + (result.error || '未知错误');
            resetProgress();
        }
    } catch (error) {
        clearTimeout(timeoutId);
        if(error.name === 'AbortError') {
            statusMessage.textContent = '请求超时，请尝试较小文件';
            resultSection.innerHTML = `<div class="error">分析超时（30分钟），建议：<br>1. 检查视频长度<br>2. 尝试更小尺寸的视频文件</div>`;
        }else {
            statusMessage.textContent = '分析出错：' + error.message;
        }
        resetProgress();
    }
}

// 绑定新的事件监听
document.querySelector('.vision-analysis').addEventListener('click', handleVisionAnalysis);
document.querySelector('.behavior-analysis').addEventListener('click', handleBehaviorAnalysis);

function updateProgress(step, status) {
    const stepElement = document.querySelector(`[data-step="${step}"]`);
    if (stepElement) {
        // 移除所有状态类
        stepElement.classList.remove('active', 'completed');
        // 添加新状态
        stepElement.classList.add(status);
    }
}

function resetProgress() {
    const steps = document.querySelectorAll('.progress-step');
    steps.forEach(step => {
        step.classList.remove('active', 'completed');
    });
    document.querySelector('.progress-container').style.display = 'none';
} 

async function handleBehaviorAnalysis() {
    const statusMessage = document.querySelector('.status-message');
    const prompt = document.querySelector('.prompt-input').value;
    const description = document.querySelector('.description').textContent;

    try {
        updateProgress('behavior', 'active');
        statusMessage.textContent = '正在进行儿童行为分析...';
        
        const response = await fetch('/api/behavior-analysis', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                description: description,
                prompt: prompt
                // model: document.getElementById('modelSelect').value
            })
        });

        const result = await response.json();
        
        if(result.code === 200) {
            updateProgress('behavior', 'completed');
            document.querySelector('.analysis').innerHTML = marked.parse(result.data.analysis);
            statusMessage.textContent = '行为分析完成！';
        }
    } catch (error) {
        statusMessage.textContent = '分析出错：' + error.message;
        resetProgress();
    }
}