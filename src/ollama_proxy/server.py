from fastapi import FastAPI, HTTPException
import asyncio
from contextlib import asynccontextmanager
from .define import ChatRequest
from .services import create_model_service
import toml
from fastapi.responses import StreamingResponse, JSONResponse
from .services.base import BaseModelService


shutdown_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用的生命周期管理器，用于处理启动和关闭事件。
    """
    try:
        yield
    finally:
        print("Shutting down...")
        shutdown_event.set()
        await asyncio.sleep(1)  # 给其他任务一些时间来清理
        print("All tasks cancelled.")


def create_app(config_file: str = "keys.toml"):
    try:
        # 读取配置文件
        models_list = toml.load(open(config_file, "r"))

        app = FastAPI(lifespan=lifespan)

        @app.post("/api/chat")
        async def chat(request: ChatRequest):
            # 解析模型名称
            model_name = request.model
            if ":" in model_name:
                model_parts = model_name.split(":")
                model_name = f"{model_parts[0]}-{model_parts[1]}"
            elif model_name.endswith(":latest"):
                model_name = model_name[:-7]  # 移除 ':latest' 后缀

            # 更新请求中的模型名称
            request.model = model_name

            # 获取模型配置
            model_config = models_list.get(request.model)

            if not model_config:
                return {"error": f"模型 {request.model} 未配置"}

            provider = model_config.get("provider")
            service_url = model_config.get("url")
            api_key = model_config.get("api_key")

            model_service = create_model_service(provider, service_url, api_key)

            # 直接使用 model_service.stream_chat 作为生成器
            stream_generator = model_service.stream_chat(
                request.messages, **request.kwargs
            )

            # 返回流式响应
            return StreamingResponse(stream_generator, media_type="text/event-stream")

        @app.get("/api/tags")
        async def list_models():
            """
            列出所有可用的模型。
            """
            print("开始处理 /api/tags 请求")

            # 假设我们使用默认的模型配置
            default_config = next(iter(models_list.values()), None)
            print(f"默认配置: {default_config}")

            if not default_config:
                print("未找到模型配置")
                raise HTTPException(status_code=404, detail="模型配置未找到")

            provider = default_config.get("provider")
            service_url = default_config.get("url")
            api_key = default_config.get("api_key")
            print(
                f"提供者: {provider}, 服务URL: {service_url}, API密钥: {'已设置' if api_key else '未设置'}"
            )

            try:
                print("尝试创建模型服务")
                model_service = create_model_service(provider, service_url, api_key)
                print(f"创建的模型服务类型: {type(model_service)}")

                if not isinstance(model_service, BaseModelService):
                    print("不支持的服务类型")
                    raise HTTPException(status_code=400, detail="不支持的服务类型")

                print("开始列出模型")
                models = await model_service.list_models()
                print(f"获取到的模型列表: {models}")

                return JSONResponse(content={"models": models})
            except Exception as e:
                print(f"发生异常: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))

        return app
    except Exception as e:
        print(f"创建应用时发生错误: {str(e)}")
        raise  # 重新抛出异常，以便调用者知道发生了错误
