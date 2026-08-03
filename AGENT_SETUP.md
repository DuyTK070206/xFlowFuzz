# Chạy XFlowFuzz với OpenAI agent

## 1. Cài thư viện

```bash
pip install -r requirements.txt
```

## 2. Tạo file `.env`

Sao chép `.env.example` thành `.env` rồi điền API key:

```env
OPENAI_API_KEY=sk-your-real-key
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0
AGENT_MAX_STEPS=8
```

Không commit `.env` lên GitHub.

## 3. Chạy demo không cần API

```bash
python demo.py
```

## 4. Chạy agent thật

```bash
python demo_agent.py
```

`demo_agent.py` dùng OpenAI Function Calling để agent tự chọn và gọi các tool
đã đăng ký trong `subjects/`.

## Các file liên quan

- `runner/openai_client.py`: adapter OpenAI.
- `config.py`: đọc cấu hình từ biến môi trường.
- `.env.example`: mẫu cấu hình.
- `demo_agent.py`: chạy agent thật.
- `demo.py`: chạy offline bằng fake LLM.
