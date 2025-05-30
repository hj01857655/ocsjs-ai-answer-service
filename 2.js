// ==UserScript==
// @name         超星自动采集
// @namespace    http://tampermonkey.net/
// @version      0.3
// @description  超星自动采集 - 支持单个考试页面和考试列表页面
// @author       You
// @match        https://mooc2-ans.chaoxing.com/mooc2-ans/work/dowork*
// @match        https://mooc2-ans.chaoxing.com/mooc2-ans/exam/lookpaper*
// @icon         https://www.google.com/s2/favicons?sz=64&domain=chaoxing.com
// @grant        none
// @require      https://unpkg.com/layui@2.11.2/dist/layui.js
// ==/UserScript==

(function () {
    'use strict';

    // 检测当前页面类型
    const isExamPage = location.href.includes('/exam/lookpaper');
    const isExamListPage = isExamPage && document.querySelector('.dataBody');
    const isExamDetailPage = isExamPage && document.querySelector('.stem_con');

    // 创建全局状态对象
    const state = {
        examLinks: [],
        currentExamIndex: 0,
        isCollecting: false,
        totalCollected: 0,
        startTime: null
    };

    // 根据页面类型执行不同的初始化
    if (isExamListPage) {
        console.log('检测到考试列表页面');
        initExamListPage();
    } else if (isExamDetailPage) {
        console.log('检测到考试详情页面');
        initExamDetailPage();
    } else {
        console.log('未知页面类型');
        return;
    }

    // 考试列表页面初始化函数
    function initExamListPage() {
        // 防止重复添加按钮
        if (document.getElementById('batch-collect-btn')) return;

        // 收集所有考试链接
        collectExamLinks();

        // 检查是否满足自动开始批量采集的条件
        const autoStartParam = new URLSearchParams(window.location.search).get('autostart');
        const hasAutoStartFlag = autoStartParam === 'true' || autoStartParam === '1';
        const hasEnoughExams = state.examLinks.length > 0;

        // 如果满足自动开始条件，延迟一秒后自动开始批量采集
        if (hasAutoStartFlag && hasEnoughExams) {
            console.log('检测到autostart参数，将自动开始批量采集...');
            setTimeout(() => {
                startBatchCollection(true); // 传入true表示自动模式
            }, 1000);
        }

        // 创建批量采集按钮
        const batchBtn = document.createElement('button');
        batchBtn.id = 'batch-collect-btn';
        batchBtn.textContent = `批量采集题目 (${state.examLinks.length} 个考试)`;
        Object.assign(batchBtn.style, {
            position: 'fixed',
            right: '30px',
            bottom: '30px',
            zIndex: 9999,
            padding: '10px 20px',
            background: '#409EFF',
            color: '#fff',
            border: 'none',
            borderRadius: '5px',
            cursor: 'pointer',
            fontWeight: 'bold',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
        });
        document.body.appendChild(batchBtn);

        // 创建状态提示
        const statusTip = document.createElement('div');
        statusTip.id = 'batch-status-tip';
        statusTip.style.display = 'none';
        Object.assign(statusTip.style, {
            position: 'fixed',
            top: '10px',
            left: '50%',
            transform: 'translateX(-50%)',
            padding: '10px 20px',
            background: 'rgba(0, 0, 0, 0.7)',
            color: '#fff',
            borderRadius: '5px',
            zIndex: '9999',
            boxShadow: '0 2px 10px rgba(0, 0, 0, 0.2)',
            fontWeight: 'bold',
            textAlign: 'center'
        });
        document.body.appendChild(statusTip);

        // 添加批量采集点击事件
        batchBtn.onclick = startBatchCollection;
    }

    // 收集考试链接函数
    function collectExamLinks() {
        state.examLinks = [];

        // 从页面中获取所有考试链接
        const links = document.querySelectorAll('.random_opera_td_20 a.look_td');

        if (links.length === 0) {
            console.warn('没有找到考试链接');
            return;
        }

        // 将相对路径转换为完整URL
        links.forEach((link, index) => {
            const href = link.getAttribute('href');
            const fullUrl = new URL(href, window.location.origin).href;
            const examName = link.closest('.randomBody_td').querySelector('.random_name_td').textContent.trim();

            state.examLinks.push({
                url: fullUrl,
                name: examName,
                index: index + 1
            });
        });

        console.log(`共找到 ${state.examLinks.length} 个考试链接:`, state.examLinks);
    }

    // 开始批量采集函数
    function startBatchCollection() {
        if (state.isCollecting) {
            alert('正在采集中，请等待当前采集完成');
            return;
        }

        if (state.examLinks.length === 0) {
            alert('没有可采集的考试链接');
            return;
        }

        // 确认是否开始批量采集
        const confirmMsg = `确定要开始批量采集 ${state.examLinks.length} 个考试的题目吗？\n\n注意：\n1. 请不要关闭浏览器或刷新页面\n2. 采集过程中会自动打开新窗口`;

        if (!confirm(confirmMsg)) return;

        // 初始化采集状态
        state.isCollecting = true;
        state.currentExamIndex = 0;
        state.totalCollected = 0;
        state.startTime = new Date();

        // 显示状态提示
        const statusTip = document.getElementById('batch-status-tip');
        statusTip.style.display = 'block';
        statusTip.textContent = `开始批量采集: 共 ${state.examLinks.length} 个考试`;

        // 开始采集第一个考试
        processNextExam();
    }

    // 处理下一个考试
    function processNextExam() {
        if (!state.isCollecting) return;

        // 检查是否已完成所有考试
        if (state.currentExamIndex >= state.examLinks.length) {
            finishBatchCollection();
            return;
        }

        const currentExam = state.examLinks[state.currentExamIndex];
        const statusTip = document.getElementById('batch-status-tip');

        // 更新状态提示
        statusTip.textContent = `正在采集: ${currentExam.name} (${state.currentExamIndex + 1}/${state.examLinks.length})`;

        // 在新标签页中打开考试
        sessionStorage.setItem('batchCollection', 'true');
        sessionStorage.setItem('batchCollectionIndex', state.currentExamIndex.toString());
        sessionStorage.setItem('currentProcessingIndex', state.currentExamIndex.toString());

        // 打开新窗口
        const examWindow = window.open(currentExam.url, '_blank');

        // 检查窗口是否打开成功
        if (!examWindow) {
            alert('无法打开新窗口，请允许浏览器打开弹出窗口');
            state.isCollecting = false;
            statusTip.style.display = 'none';
            return;
        }

        state.currentExamIndex++;

        // 设置超时时间，针对不同类型的考试可能需要不同的超时时间
        let timeoutDuration = 60000; // 默计60秒

        // 根据考试名称判断可能的复杂度
        if (currentExam.name.includes('期末') || currentExam.name.includes('期中') || currentExam.name.includes('综合')) {
            // 期中期末或综合考试可能题目较多，给更长时间
            timeoutDuration = 120000; // 2分钟
        }

        // 设置超时定时器
        const timeoutId = setTimeout(() => {
            // 检查是否还在采集当前考试
            if (state.isCollecting && state.currentExamIndex === state.examLinks.indexOf(currentExam) + 1) {
                console.log(`安全机制触发: 考试 ${currentExam.name} 超时，自动继续下一个`);

                // 尝试关闭子窗口
                try {
                    if (examWindow && !examWindow.closed) {
                        examWindow.close();
                    }
                } catch (e) {
                    console.error('关闭超时窗口失败:', e);
                }

                // 继续下一个考试
                processNextExam();
            }
        }, timeoutDuration);
    }

    // 完成批量采集
    function finishBatchCollection() {
        state.isCollecting = false;

        const endTime = new Date();
        const timeUsed = ((endTime - state.startTime) / 1000 / 60).toFixed(2);

        const statusTip = document.getElementById('batch-status-tip');
        statusTip.textContent = `批量采集完成! 共采集 ${state.totalCollected} 道题目, 耗时 ${timeUsed} 分钟`;
        statusTip.style.background = 'rgba(40, 167, 69, 0.9)';

        // 5秒后隐藏状态提示
        setTimeout(() => {
            statusTip.style.animation = 'fadeOut 0.5s forwards';
            const fadeStyle = document.createElement('style');
            fadeStyle.textContent = `
                @keyframes fadeOut {
                    from { opacity: 1; transform: translateX(-50%) translateY(0); }
                    to { opacity: 0; transform: translateX(-50%) translateY(-20px); }
                }
            `;
            document.head.appendChild(fadeStyle);
            setTimeout(() => statusTip.style.display = 'none', 500);
        }, 5000);
    }

    // 考试详情页面初始化函数
    function initExamDetailPage() {
        // 移除左侧菜单
        $("#lookLeft").remove();
        // 添加选中状态
        $(".check_dx").addClass("checked_dx")
        // 显示答案
        $(".answerDiv").show();
        // 防止重复添加按钮
        if (document.getElementById('my-question-btn')) return;

        // 检查是否来自自动采集
        const isFromBatchCollection = sessionStorage.getItem('batchCollection') === 'true';

        if (isFromBatchCollection) {
            console.log('检测到来自批量采集的请求，自动开始采集');
            // 自动开始采集
            setTimeout(() => {
                autoCollectAndContinue();
            }, 1500); // 等待页面完全加载
        }

        // 创建按钮
        const btn = document.createElement('button');
        btn.id = 'my-question-btn';
        btn.textContent = '开始采集';
        Object.assign(btn.style, {
            position: 'fixed',
            right: '30px',
            bottom: '30px',
            zIndex: 9999,
            padding: '10px 20px',
            background: '#409EFF',
            color: '#fff',
            border: 'none',
            borderRadius: '5px',
            cursor: 'pointer',
            fontWeight: 'bold',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
        });
        document.body.appendChild(btn);

        // 创建自动导入标记
        const autoImportFlag = document.createElement('div');
        autoImportFlag.className = 'auto-import-flag';
        autoImportFlag.style.display = 'none';
        document.body.appendChild(autoImportFlag);

        // 创建状态提示
        const statusTip = document.createElement('div');
        statusTip.style.position = 'fixed';
        statusTip.style.top = '10px';
        statusTip.style.left = '50%';
        statusTip.style.transform = 'translateX(-50%)';
        statusTip.style.padding = '10px 20px';
        statusTip.style.background = 'rgba(0, 0, 0, 0.7)';
        statusTip.style.color = '#fff';
        statusTip.style.borderRadius = '5px';
        statusTip.style.zIndex = '9999';
        statusTip.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.2)';
        statusTip.style.fontWeight = 'bold';
        statusTip.textContent = '自动采集中...';
        document.body.appendChild(statusTip);

        // 快速自动采集和导入功能 - 减少延时
        setTimeout(() => {
            console.log('快速自动采集已启动');
            // 直接调用采集函数而不是点击按钮，避免额外的DOM操作
            const questions = parseQuestionsFromPage();
            if (!questions.length) {
                layer && layer.msg ? layer.msg('未采集到题目') : alert('未采集到题目');
                return;
            }

            console.log(`快速采集完成，共 ${questions.length} 道题目，直接开始导入`);
            statusTip.textContent = `正在导入 ${questions.length} 道题目...`;

            // 直接发送请求，跳过预览弹窗步骤
            (async () => {
                try {
                    const startTime = new Date();
                    let body = { questions };
                    console.log('发送数据:', JSON.stringify(body).substring(0, 200) + '...');

                    // 定义多个API端点，提高连接可靠性
                    const apiEndpoints = [
                        'http://localhost:5000/api/questions/add',
                        'http://127.0.0.1:5000/api/questions/add'
                    ];

                    // 添加重试机制
                    const maxRetries = 2;
                    let retryCount = 0;
                    let resp = null;
                    let lastError = null;

                    // 重试循环
                    while (retryCount <= maxRetries && !resp) {
                        // 如果不是第一次尝试，显示重试信息
                        if (retryCount > 0) {
                            statusTip.textContent = `连接失败，正在重试 (${retryCount}/${maxRetries})...`;
                            // 等待一秒后重试
                            await new Promise(resolve => setTimeout(resolve, 1000));
                        }

                        // 尝试所有端点
                        for (const endpoint of apiEndpoints) {
                            try {
                                statusTip.textContent = `正在连接到 ${endpoint.split('/')[2]}...`;
                                resp = await fetch(endpoint, {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json'
                                    },
                                    credentials: 'include',
                                    body: JSON.stringify(body)
                                });

                                // 如果成功连接，跳出循环
                                if (resp) break;
                            } catch (e) {
                                console.warn(`连接到 ${endpoint} 失败:`, e);
                                lastError = e;
                                // 继续尝试下一个端点
                            }
                        }

                        retryCount++;
                    }

                    // 如果所有端点和重试都失败
                    if (!resp) {
                        throw lastError || new Error('无法连接到任何API端点');
                    }

                    let result = await resp.json();
                    const endTime = new Date();
                    const timeUsed = (endTime - startTime) / 1000;

                    if (resp.ok) {
                        console.log(`快速录入成功! 耗时: ${timeUsed}秒, 响应结果:`, result);
                        // 成功提示使用定制样式
                        layer.open({
                            type: 1,
                            title: false,
                            closeBtn: false,
                            shade: 0.3,
                            area: ['400px', 'auto'],
                            skin: 'success-notification',
                            time: 3000, // 3秒后自动关闭
                            anim: 2, // 使用滑动动画
                            shadeClose: true,
                            content: `<div style="padding: 20px; text-align: center; background: linear-gradient(135deg, #28a745, #20c997); border-radius: 10px; box-shadow: 0 10px 30px rgba(40, 167, 69, 0.3);">
                            <div style="font-size: 60px; margin-bottom: 10px; color: white;"><i class="layui-icon layui-icon-ok-circle"></i></div>
                            <div style="font-size: 22px; font-weight: bold; color: white; margin-bottom: 5px;">快速录入成功!</div>
                            <div style="color: rgba(255,255,255,0.9); font-size: 16px;">${result.message}</div>
                            <div style="margin-top: 15px; color: rgba(255,255,255,0.8); font-size: 14px;">共导入 ${questions.length} 道题目，耗时 ${timeUsed} 秒</div>
                        </div>`
                        });

                        // 更新状态提示
                        statusTip.textContent = `快速导入成功: ${questions.length} 道题目`;
                        statusTip.style.background = 'rgba(40, 167, 69, 0.9)';
                        statusTip.style.boxShadow = '0 4px 20px rgba(40, 167, 69, 0.4)';
                    } else {
                        console.error(`录入失败! 耗时: ${timeUsed}秒, 错误:`, result);
                        layer.msg(result.message || '录入失败', { icon: 2 });
                        statusTip.textContent = `导入失败: ${result.message || '未知错误'}`;
                        statusTip.style.background = 'rgba(220, 53, 69, 0.9)';
                    }

                    // 5秒后消失
                    setTimeout(() => {
                        statusTip.style.animation = 'fadeOut 0.5s forwards';
                        setTimeout(() => statusTip.style.display = 'none', 500);
                    }, 5000);
                } catch (e) {
                    console.error('录入题目失败，错误信息:', e);
                    layer.msg('网络错误，录入失败！');
                    statusTip.textContent = `导入失败: 网络错误`;
                    statusTip.style.background = 'rgba(220, 53, 69, 0.9)';
                }
            })();
        }, 500); // 减少等待时间，加快启动

        btn.onclick = function () {
            let questions = parseQuestionsFromPage();
            if (!questions.length) {
                layer && layer.msg ? layer.msg('未采集到题目') : alert('未采集到题目');
                return;
            }
            // 格式化预览HTML
            let html = renderQuestionsPreview(questions);
            layui.use('layer', function () {
                let layer = layui.layer;
                layer.open({
                    type: 1,
                    title: '<div style="display:flex;align-items:center;gap:10px;font-size:18px;font-weight:500;line-height:1.2;min-height:32px;">'
                        + '<img src="https://img1.imgtp.com/2023/07/16/2Qv7Qw1b.png" style="width:22px;height:22px;vertical-align:middle;">'
                        + '<span>采集题目预览</span>'
                        + '</div>',
                    closeBtn: 1,
                    area: ['750px', '520px'],
                    content: `<div id="plum-bg" style="position:relative;min-height:420px;">${html}</div>` +
                        `<style>
                    #plum-bg::before {
                        content: '';
                        position: absolute;
                        left: 0; top: 0; right: 0; bottom: 0;
                        background: url('https://img1.imgtp.com/2023/07/16/2Qv7Qw1b.png') repeat center center;
                        opacity: 0.07;
                        pointer-events: none;
                        z-index: 0;
                    }
                    #plum-bg table {
                        border-radius: 14px;
                        box-shadow: 0 4px 24px 0 rgba(120,80,160,0.13);
                        overflow: hidden;
                        background: rgba(255,255,255,0.97);
                        font-size: 15px;
                    }
                    #plum-bg th {
                        background: linear-gradient(90deg,#f5f7fa 60%,#f0e6f6 100%);
                        color: #6d3b7b;
                        font-weight: 600;
                        border-bottom: 2px solid #e0d7f3;
                    }
                    #plum-bg tr:hover {background: #f0f6ff;}
                    #plum-bg th, #plum-bg td {
                        transition: background 0.2s;
                        padding: 8px 10px;
                    }
                    #plum-bg td {
                        border:1px solid #eee;
                        border-left: none;
                        border-right: none;
                    }
                    .layui-layer-content { border-radius: 16px!important; }
                    .layui-layer { box-shadow: 0 8px 32px 0 rgba(120,80,160,0.18)!important; border-radius: 18px!important; }
                    .layui-layer-title { font-size:18px!important; font-weight:500; background:linear-gradient(90deg,#fff 60%,#f0e6f6 100%)!important; color:#6d3b7b!important; border-radius: 18px 18px 0 0!important; min-height: 32px; display: flex; align-items: center; gap: 10px;}
                    .layui-layer-setwin { right: 16px!important; top: 16px!important; }
                    .layui-layer-setwin .layui-layer-close1 { font-size:22px!important; color:#b08bc7!important; }
                    .layui-layer-btn {
                        padding-bottom: 18px !important;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        gap: 0;
                    }
                    .layui-layer-btn .layui-layer-btn0 {
                        background: linear-gradient(90deg,#8f6ed5 0%,#4e8cff 100%);
                        color: #fff !important;
                        border: none !important;
                        border-radius: 12px !important;
                        font-size: 17px;
                        font-weight: 700;
                        box-shadow: 0 4px 16px 0 rgba(120,80,160,0.18);
                        padding: 0 38px;
                        height: 44px;
                        min-width: 120px;
                        margin: 0 12px 0 0;
                        transition: background 0.2s, box-shadow 0.2s, transform 0.1s;
                        outline: none;
                    }
                    .layui-layer-btn .layui-layer-btn0:hover, .layui-layer-btn .layui-layer-btn0:focus {
                        background: linear-gradient(90deg,#4e8cff 0%,#8f6ed5 100%);
                        box-shadow: 0 8px 32px 0 rgba(120,80,160,0.22);
                        transform: translateY(-2px) scale(1.04);
                    }
                    .layui-layer-btn .layui-layer-btn1 {
                        background: #f5f7fa !important;
                        color: #8f6ed5 !important;
                        border: 1.5px solid #e0d7f3 !important;
                        border-radius: 12px !important;
                        font-size: 16px;
                        font-weight: 500;
                        min-width: 100px;
                        height: 44px;
                        margin-left: 0;
                        margin-right: 12px;
                        transition: background 0.2s, color 0.2s, border 0.2s, transform 0.1s;
                        outline: none;
                    }
                    .layui-layer-btn .layui-layer-btn1:hover, .layui-layer-btn .layui-layer-btn1:focus {
                        background: #e6e6f7 !important;
                        color: #6d3b7b !important;
                        border: 1.5px solid #b08bc7 !important;
                        transform: translateY(-1px) scale(1.03);
                    }
                    @media (max-width: 600px) {
                        .layui-layer-btn .layui-layer-btn0, .layui-layer-btn .layui-layer-btn1 {
                            min-width: 80px;
                            font-size: 15px;
                            padding: 0 12px;
                            height: 38px;
                        }
                    }
                    </style>`,
                    btn: ['确定导入', '取消'],
                    btnAlign: 'c',
                    yes: async function (index) {
                        try {
                            const isAutoImport = document.querySelector('.auto-import-flag') !== null;
                            console.log(`开始录入题目到数据库，共 ${questions.length} 道题目${isAutoImport ? ' (自动导入模式)' : ''}`);

                            // 记录开始时间

                            if (!questions || questions.length === 0) {
                                console.warn('未找到可采集的题目');
                                closeAndContinue(0);
                                return;
                            }

                            // 记录开始时间
                            const startTime = new Date();

                            // 发送数据到服务器
                            let body = { questions };
                            console.log('发送数据:', JSON.stringify(body).substring(0, 200) + '...');

                            // 定义多个API端点，提高连接可靠性
                            const apiEndpoints = [
                                'http://localhost:5000/api/questions/add',
                                'http://127.0.0.1:5000/api/questions/add'
                            ];

                            // 添加重试机制
                            const maxRetries = 2;
                            let retryCount = 0;
                            let resp = null;
                            let lastError = null;

                            // 重试循环
                            while (retryCount <= maxRetries && !resp) {
                                // 如果不是第一次尝试，显示重试信息
                                if (retryCount > 0) {
                                    layer.msg(`连接失败，正在重试 (${retryCount}/${maxRetries})...`);
                                    // 等待一秒后重试
                                    await new Promise(resolve => setTimeout(resolve, 1000));
                                }

                                // 尝试所有端点
                                for (const endpoint of apiEndpoints) {
                                    try {
                                        layer.msg(`正在连接到 ${endpoint.split('/')[2]}...`);
                                        resp = await fetch(endpoint, {
                                            method: 'POST',
                                            headers: {
                                                'Content-Type': 'application/json'
                                            },
                                            credentials: 'include',
                                            body: JSON.stringify(body)
                                        });

                                        // 如果成功连接，跳出循环
                                        if (resp) break;
                                    } catch (e) {
                                        console.warn(`连接到 ${endpoint} 失败:`, e);
                                        lastError = e;
                                        // 继续尝试下一个端点
                                    }
                                }

                                retryCount++;
                            }

                            // 如果所有端点和重试都失败
                            if (!resp) {
                                throw lastError || new Error('无法连接到任何API端点');
                            }

                            let result = await resp.json();
                            const endTime = new Date();
                            const timeUsed = (endTime - startTime) / 1000;

                            if (resp.ok) {
                                console.log(`录入成功! 耗时: ${timeUsed}秒, 响应结果:`, result);
                                const message = result.message || '录入成功';

                                // 成功提示使用定制样式
                                layer.open({
                                    type: 1,
                                    title: false,
                                    closeBtn: false,
                                    shade: 0.3,
                                    area: ['400px', 'auto'],
                                    skin: 'success-notification',
                                    time: 3000, // 3秒后自动关闭
                                    anim: 2, // 使用滑动动画
                                    shadeClose: true,
                                    content: `<div style="padding: 20px; text-align: center; background: linear-gradient(135deg, #28a745, #20c997); border-radius: 10px; box-shadow: 0 10px 30px rgba(40, 167, 69, 0.3);">
                                        <div style="font-size: 60px; margin-bottom: 10px; color: white;"><i class="layui-icon layui-icon-ok-circle"></i></div>
                                        <div style="font-size: 22px; font-weight: bold; color: white; margin-bottom: 5px;">录入成功!</div>
                                        <div style="color: rgba(255,255,255,0.9); font-size: 16px;">${message}</div>
                                        <div style="margin-top: 15px; color: rgba(255,255,255,0.8); font-size: 14px;">共导入 ${questions.length} 道题目，耗时 ${timeUsed} 秒</div>
                                    </div>`
                                });
                            } else {
                                // 失败提示使用普通layer.msg
                                console.error(`录入失败! 耗时: ${timeUsed}秒, 错误:`, result);
                                const message = result.message || '录入失败';
                                layer.msg(message, { icon: 2 });
                            }

                            // 如果是自动导入模式，更新状态提示
                            const statusTip = document.querySelector('div[style*="position: fixed"][style*="top: 10px"]');
                            if (statusTip) {
                                if (resp.ok) {
                                    statusTip.textContent = `自动导入成功: ${questions.length} 道题目`;
                                    statusTip.style.background = 'rgba(40, 167, 69, 0.9)';
                                    statusTip.style.boxShadow = '0 4px 20px rgba(40, 167, 69, 0.4)';
                                    statusTip.style.animation = 'pulse 1.5s infinite';
                                    // 添加动画样式
                                    const style = document.createElement('style');
                                    style.textContent = `
                                        @keyframes pulse {
                                            0% { transform: translateX(-50%) scale(1); }
                                            50% { transform: translateX(-50%) scale(1.05); }
                                            100% { transform: translateX(-50%) scale(1); }
                                        }
                                    `;
                                    document.head.appendChild(style);
                                } else {
                                    statusTip.textContent = `自动导入失败: ${result.message || '未知错误'}`;
                                    statusTip.style.background = 'rgba(220, 53, 69, 0.9)';
                                }
                                setTimeout(() => {
                                    statusTip.style.animation = 'fadeOut 0.5s forwards';
                                    // 添加消失动画
                                    const fadeStyle = document.createElement('style');
                                    fadeStyle.textContent = `
                                        @keyframes fadeOut {
                                            from { opacity: 1; transform: translateX(-50%) translateY(0); }
                                            to { opacity: 0; transform: translateX(-50%) translateY(-20px); }
                                        }
                                    `;
                                    document.head.appendChild(fadeStyle);
                                    setTimeout(() => statusTip.style.display = 'none', 500);
                                }, 5000);
                            }
                        } catch (e) {
                            console.error('录入题目失败，错误信息:', e);
                            layer.msg('网络错误，录入失败！');
                        }
                    }
                });
            });
        };

        // 自动采集页面题目函数
        function parseQuestionsFromPage() {
            let questions = [];
            $('.stem_con').each(function () {
                // 题型识别
                let typeText = $(this).find('span.colorShallow').text();
                let type = 'single';
                if (/多选/.test(typeText)) type = 'multiple';
                else if (/判断/.test(typeText)) type = 'judgement';
                else if (/填空/.test(typeText)) type = 'completion';
                else if (/简答/.test(typeText)) type = 'short';

                // 题干（合并所有非空p，防止空p导致题干丢失）
                let question = $(this).find('p').map(function () { return $(this).text().trim(); }).get().filter(Boolean).join(' ');

                // 选项：只有选择题（单选和多选）才有选项部分
                let $answerBlock = $(this).next('.stem_answer');
                let options = [];
                let optionMap = {};
                // 只有选择题才处理选项
                if ((type === 'single' || type === 'multiple') && $answerBlock.length) {
                    $answerBlock.find('.num_option').each(function (i, el) {
                        let letter = $(el).text().replace(/[.．、]/, '').trim();
                        let content = $(el).next('.answer_p').text().trim() || $(el).next().text().trim();
                        options.push(letter + '.' + content);
                        optionMap[letter] = content;
                    });
                }

                // 答案：根据题型不同，获取答案区域
                let $answerDiv;
                if (type === 'single' || type === 'multiple') {
                    // 选择题：取 .stem_answer 的下一个兄弟 .answerDiv
                    $answerDiv = $answerBlock.length ? $answerBlock.next('.answerDiv') : $();
                } else {
                    // 非选择题：直接从题干区域获取下一个兄弟 .answerDiv
                    $answerDiv = $(this).next('.stem_answer').next('.answerDiv');
                    if (!$answerDiv.length) {
                        $answerDiv = $(this).next('.answerDiv');
                    }
                }
                let answer = '';
                if (type === 'single' || type === 'multiple') {
                    let ansText = $answerDiv.find('.answer_tit p').text().trim().replace(/[^A-Z]/ig, '');
                    let ansArr = ansText.split('');
                    let ansContentArr = ansArr.map(l => optionMap[l] || l);
                    answer = ansContentArr.join(';');
                } else if (type === 'completion') {
                    let blanks = [];
                    $answerDiv.find('.tiankong_con .ans-wid-cRight p').each(function () {
                        let v = $(this).text().trim();
                        if (v) blanks.push(v);
                    });
                    if (!blanks.length) {
                        $answerDiv.find('p').each(function () {
                            let v = $(this).text().trim();
                            if (v) blanks.push(v);
                        });
                    }
                    answer = blanks.join(';');
                } else if (type === 'judgement') {
                    answer = $answerDiv.find('.answer_tit p').text().trim();
                    if (!answer) {
                        answer = $answerDiv.find('p').text().trim();
                    }
                    if (/^(对|正确|true|√)$/i.test(answer)) answer = '正确';
                    if (/^(错|错误|false|×)$/i.test(answer)) answer = '错误';
                } else if (type === 'short') {
                    let ansArr = [];
                    $answerDiv.find('.ans-wid-cRight p').each(function () {
                        let v = $(this).text().trim();
                        if (v) ansArr.push(v);
                    });
                    if (!ansArr.length) {
                        let v = $answerDiv.find('.ans-wid-cRight').text().trim();
                        if (v) ansArr.push(v);
                    }
                    answer = ansArr.filter(Boolean).join('\n');
                } else {
                    answer = $answerDiv.find('p').map(function () { return $(this).text().trim(); }).get().filter(Boolean).join(';');
                }

                // 只有选择题（单选和多选）才包含选项部分
                if (type === 'single' || type === 'multiple') {
                    questions.push({
                        question,
                        type,
                        options: options.join(';'),
                        answer
                    });
                } else {
                    // 其他题型（判断题、填空题、简答题）不包含选项
                    questions.push({
                        question,
                        type,
                        answer
                    });
                }
            });
            return questions;
        }

        // 自动采集并继续下一个考试
        function autoCollectAndContinue() {
            try {
                // 检查是否有题目可采集
                const questions = parseQuestionsFromPage();

                if (!questions || questions.length === 0) {
                    console.warn('未找到可采集的题目');
                    closeAndContinue(0);
                    return;
                }

                console.log(`自动采集到 ${questions.length} 道题目，开始导入`);

                // 创建状态提示
                const statusTip = document.createElement('div');
                statusTip.style.position = 'fixed';
                statusTip.style.top = '10px';
                statusTip.style.left = '50%';
                statusTip.style.transform = 'translateX(-50%)';
                statusTip.style.padding = '10px 20px';
                statusTip.style.background = 'rgba(0, 0, 0, 0.7)';
                statusTip.style.color = '#fff';
                statusTip.style.borderRadius = '5px';
                statusTip.style.zIndex = '9999';
                statusTip.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.2)';
                statusTip.style.fontWeight = 'bold';
                statusTip.textContent = `正在导入 ${questions.length} 道题目...`;
                document.body.appendChild(statusTip);

                // 直接发送请求导入题目
                (async () => {
                    try {
                        const startTime = new Date();
                        let body = { questions };

                        // 定义API端点，支持多个备选地址
                        const apiEndpoints = [
                            'http://localhost:5000/api/questions/add',
                            'http://127.0.0.1:5000/api/questions/add'
                        ];

                        // 尝试所有端点，直到成功或全部失败
                        let resp = null;
                        let lastError = null;

                        for (const endpoint of apiEndpoints) {
                            try {
                                statusTip.textContent = `正在连接到 ${endpoint.split('/')[2]}...`;
                                resp = await fetch(endpoint, {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json'
                                    },
                                    credentials: 'include',
                                    body: JSON.stringify(body)
                                });

                                // 如果成功连接，跳出循环
                                if (resp) break;
                            } catch (e) {
                                console.warn(`连接到 ${endpoint} 失败:`, e);
                                lastError = e;
                                // 继续尝试下一个端点
                            }
                        }

                        // 如果所有端点都失败
                        if (!resp) {
                            throw lastError || new Error('无法连接到任何API端点');
                        }

                        let result = await resp.json();
                        const endTime = new Date();
                        const timeUsed = (endTime - startTime) / 1000;

                        if (resp.ok) {
                            console.log(`自动录入成功! 耗时: ${timeUsed}秒, 响应结果:`, result);
                            statusTip.textContent = `导入成功: ${questions.length} 道题目, 耗时 ${timeUsed} 秒`;
                            statusTip.style.background = 'rgba(40, 167, 69, 0.9)';

                            // 在关闭前等待一下，确保用户可以看到成功信息
                            setTimeout(() => {
                                closeAndContinue(questions.length);
                            }, 1000);
                        } else {
                            console.error(`自动录入失败! 耗时: ${timeUsed}秒, 错误:`, result);
                            statusTip.textContent = `导入失败: ${result.message || '未知错误'}`;
                            statusTip.style.background = 'rgba(220, 53, 69, 0.9)';

                            // 在失败时也继续下一个，但等待时间长一点
                            setTimeout(() => {
                                closeAndContinue(0);
                            }, 2000);
                        }
                    } catch (e) {
                        console.error('自动录入题目失败，错误信息:', e);
                        statusTip.textContent = `导入失败: 网络错误`;
                        statusTip.style.background = 'rgba(220, 53, 69, 0.9)';

                        // 发生异常时也继续下一个
                        setTimeout(() => {
                            closeAndContinue(0);
                        }, 2000);
                    }
                })();
            } catch (e) {
                console.error('自动采集异常:', e);
                closeAndContinue(0);
            }
        }

        // 关闭当前页面并继续下一个考试
        function closeAndContinue(collectedCount) {
            // 获取批量采集的父窗口
            const opener = window.opener;

            if (opener) {
                try {
                    // 尝试向父窗口发送消息
                    opener.postMessage({
                        type: 'examCollected',
                        collectedCount: collectedCount
                    }, '*');

                    console.log(`已发送采集完成消息，采集数量: ${collectedCount}`);

                    // 使用父窗口的函数直接处理下一个考试（双重保险）
                    try {
                        if (typeof opener.processNextExam === 'function') {
                            console.log('直接调用父窗口的processNextExam函数');
                            setTimeout(() => {
                                opener.state.totalCollected += collectedCount;
                                opener.processNextExam();
                            }, 500);
                        }
                    } catch (e) {
                        console.error('直接调用父窗口函数失败:', e);
                    }
                } catch (e) {
                    console.error('发送消息失败:', e);
                }
            }

            // 清除会话存储
            sessionStorage.removeItem('batchCollection');
            sessionStorage.removeItem('batchCollectionIndex');
            sessionStorage.removeItem('currentProcessingIndex');

            // 关闭当前窗口
            console.log('关闭当前窗口，继续下一个考试');

            // 延迟关闭，确保消息发送成功
            setTimeout(() => {
                window.close();

                // 如果窗口没有关闭（浏览器可能阻止了脚本关闭窗口）
                setTimeout(() => {
                    if (!window.closed) {
                        alert('请手动关闭此窗口以继续采集下一个考试');
                    }
                }, 1000);
            }, 500);
        }

        // 格式化题目预览
        function renderQuestionsPreview(questions) {
            let html = '<div style="max-height:350px;overflow:auto;"><table style="width:100%;border-collapse:collapse;">';
            html += '<tr style="background:#f5f7fa;"><th>题干</th><th>类型</th><th>选项</th><th>答案</th></tr>';
            questions.forEach(q => {
                html += `<tr>
                <td style="border:1px solid #eee;padding:6px 8px;">${q.question}</td>
                <td style="border:1px solid #eee;padding:6px 8px;">${q.type}</td>
                <td style="border:1px solid #eee;padding:6px 8px;">${q.options || ''}</td>
                <td style="border:1px solid #eee;padding:6px 8px;">${q.answer}</td>
            </tr>`;
            });
            html += '</table></div>';
            html += `<div style="color:#888;font-size:13px;margin-top:10px;">共采集到 <b>${questions.length}</b> 道题目</div>`;
            return html;
        }

        // 添加消息监听器，接收子窗口的采集完成消息
        window.addEventListener('message', function (event) {
            if (event.data && event.data.type === 'examCollected') {
                const collectedCount = event.data.collectedCount || 0;
                console.log(`收到采集完成消息，采集数量: ${collectedCount}`);

                // 更新总采集数量
                state.totalCollected += collectedCount;

                // 更新状态提示
                const statusTip = document.getElementById('batch-status-tip');
                if (statusTip) {
                    statusTip.textContent = `正在采集: 已完成 ${state.currentExamIndex}/${state.examLinks.length}, 共采集 ${state.totalCollected} 道题目`;
                }

                // 处理下一个考试
                setTimeout(() => {
                    processNextExam();
                }, 1000);
            }
        });
    }
})();