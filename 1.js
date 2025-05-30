

// 你的 session cookie 和 veloera-user
const SESSION_COOKIE = 'session=MTc0ODMzMjg2N3xEWDhFQVFMX2dBQUJFQUVRQUFEXzN2LUFBQWNHYzNSeWFXNW5EQTBBQzI5aGRYUm9YM04wWVhSbEJuTjBjbWx1Wnd3T0FBeDNiV2RxY0hsM2FYaGpiVUVHYzNSeWFXNW5EQVFBQW1sa0EybHVkQVFEQVAtb0JuTjBjbWx1Wnd3S0FBaDFjMlZ5Ym1GdFpRWnpkSEpwYm1jTURBQUtiR2x1ZFhoa2IxODROQVp6ZEhKcGJtY01CZ0FFY205c1pRTnBiblFFQWdBQ0JuTjBjbWx1Wnd3SUFBWnpkR0YwZFhNRGFXNTBCQUlBQWdaemRISnBibWNNQndBRlozSnZkWEFHYzNSeWFXNW5EQWtBQjJSbFptRjFiSFFHYzNSeWFXNW5EQVVBQTJGbVpnWnpkSEpwYm1jTUJnQUVjSGxKVFE9PXzcP8Cmyr9T6w2OiHdNuzh41ah_FnvUflEUAGp6nQKltw==';
const VELOERA_USER = '84';

// 公共 fetch 头
const commonHeaders = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'cache-control': 'no-store',
    'priority': 'u=1, i',
    'sec-ch-ua': '"Chromium";v="136", "Microsoft Edge";v="136", "Not.A/Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'veloera-user': VELOERA_USER,
    'cookie': SESSION_COOKIE,
    'Referer': 'https://veloera.wei.bi/token',
    'Referrer-Policy': 'strict-origin-when-cross-origin'
};

const API_BASE = 'https://veloera.wei.bi';

async function getAllTokens() {
    const res = await fetch(`${API_BASE}/api/token/?p=0&size=1000`, {
        method: 'GET',
        headers: commonHeaders
    });
    const data = await res.json();
    return data.data || [];
}

async function getTokenDetail(id) {
    const res = await fetch(`${API_BASE}/api/token/${id}`, {
        method: 'GET',
        headers: commonHeaders
    });
    const data = await res.json();
    return data.data;
}

async function updateToken(token) {
    // 只保留允许修改的字段
    const putData = {
        id: token.id,
        user_id: token.user_id,
        key: token.key,
        status: token.status,
        name: token.name,
        expired_time: token.expired_time,
        remain_quota: token.remain_quota,
        unlimited_quota: token.unlimited_quota,
        model_limits_enabled: false,
        model_limits: "",
        allow_ips: token.allow_ips,
        used_quota: token.used_quota,
        group: "default"
    };
    const res = await fetch(`${API_BASE}/api/token/`, {
        method: 'PUT',
        headers: {
            ...commonHeaders,
            'content-type': 'application/json'
        },
        body: JSON.stringify(putData)
    });
    const text = await res.text();
    let result;
    try {
        result = JSON.parse(text);
    } catch {
        result = { success: false, message: text };
    }
    if (result.success) {
        console.log(`成功: ${putData.key} (${putData.name})`);
    } else {
        console.log(`失败: ${putData.key} (${putData.name}) - ${result.message}`);
    }
}

async function main() {
    const tokens = await getAllTokens();
    console.log(`共获取到 ${tokens.length} 个token`);
    for (const token of tokens) {
        try {
            const detail = await getTokenDetail(token.id);
            if (!detail) {
                console.log(`获取token ${token.id} 详情失败，跳过`);
                continue;
            }
            await updateToken(detail);
        } catch (e) {
            console.log(`处理token ${token.id} 异常:`, e);
        }
    }
}

main();