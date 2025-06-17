/**
 * 超星平台图片代理处理脚本
 * 用于解决超星平台图片403错误问题
 */

// 已处理图片的集合，避免重复处理
const processedImages = new Set();

/**
 * 处理页面中的所有图片
 */
function processImages() {
    const images = document.querySelectorAll('img');
    
    images.forEach(function(img) {
        // 如果图片已经处理过，跳过
        if (processedImages.has(img)) {
            return;
        }
        
        const src = img.getAttribute('src');
        
        // 跳过空src或已经是代理URL的图片
        if (!src || src.includes('/api/image/proxy')) {
            processedImages.add(img);
            return;
        }
        
        // 检查是否是超星平台的图片
        if (src.includes('p.ananas.chaoxing.com') || 
            src.includes('chaoxing.com') || 
            src.includes('pan-yz.chaoxing.com')) {
            
            // 标记图片已处理
            processedImages.add(img);
            
            // 保存原始图片URL
            img.setAttribute('data-original-src', src);
            
            // 创建代理URL
            const proxiedSrc = '/api/image/proxy?url=' + encodeURIComponent(src);
            
            // 添加错误处理
            img.onerror = function() {
                console.error('代理图片加载失败:', src);
                // 显示错误提示
                const errorDiv = document.createElement('div');
                errorDiv.className = 'image-error-container';
                errorDiv.innerHTML = `
                    <div class="alert alert-warning" role="alert">
                        <i class="bi bi-exclamation-triangle-fill"></i> 图片加载失败
                        <a href="${src}" target="_blank" class="alert-link">查看原图</a>
                    </div>
                `;
                
                // 替换图片
                if (img.parentNode) {
                    img.parentNode.insertBefore(errorDiv, img);
                    img.style.display = 'none';
                }
            };
            
            // 替换图片源
            img.setAttribute('src', proxiedSrc);
            
            // 添加点击事件，允许用户在新窗口中查看原图
            img.style.cursor = 'pointer';
            img.title = '点击查看原图';
            
            img.addEventListener('click', function(e) {
                e.preventDefault();
                const originalSrc = this.getAttribute('data-original-src');
                if (originalSrc) {
                    window.open(originalSrc, '_blank');
                }
            });
        }
    });
}

/**
 * 初始化图片代理功能
 */
function initImageProxy() {
    // 初始处理
    processImages();
    
    // 监听DOM变化，处理动态加载的图片
    const observer = new MutationObserver(function(mutations) {
        let hasNewImages = false;
        
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList') {
                const addedNodes = Array.from(mutation.addedNodes);
                
                // 检查是否有新添加的图片
                const hasImg = addedNodes.some(node => {
                    // 检查节点本身是否是图片
                    if (node.nodeName === 'IMG') {
                        return true;
                    }
                    
                    // 检查节点内部是否包含图片
                    if (node.nodeType === 1) { // 元素节点
                        return node.querySelector('img') !== null;
                    }
                    
                    return false;
                });
                
                if (hasImg) {
                    hasNewImages = true;
                }
            }
        });
        
        // 如果有新图片，重新处理
        if (hasNewImages) {
            processImages();
        }
    });
    
    // 配置观察器
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
}

// 当DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', initImageProxy);
