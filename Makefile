.PHONY: web cli watch help install test

# 默认端口
PORT ?= 8502
HOST ?= 127.0.0.1

help:  ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## 安装依赖
	pip install -r requirements.txt

web:  ## 启动 Streamlit Web 仪表盘
	streamlit run streamlit_app.py --server.address $(HOST) --server.port $(PORT)

cli:  ## 启动 CLI 监控（需传基金代码，如 make cli ARGS="164701 161116"）
	python cli.py $(ARGS)

watch:  ## 启动 CLI 监控（watch 模式，30s 刷新）
	python cli.py $(ARGS) --estimate --watch 30

test:  ## 运行测试
	python -m pytest tests/ -v
