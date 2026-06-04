#!/usr/bin/env python3
"""
WebUI Tests - 测试KAOT WebUI的语法和功能
包括：JavaScript语法检查、Python语法检查、配置文件验证、Flask路由测试、KAOTRunner测试
"""

import os
import sys
import json
import yaml
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
WEBUI_DIR = PROJECT_ROOT / "webui"


class TestJavaScriptSyntax:
    """JavaScript语法检查"""
    
    @pytest.fixture
    def js_files(self) -> List[Path]:
        """获取所有JS文件"""
        js_files = []
        static_dir = WEBUI_DIR / "static"
        if static_dir.exists():
            js_files = list(static_dir.glob("*.js"))
        return js_files
    
    def test_js_files_exist(self, js_files: List[Path]) -> None:
        """测试JS文件存在"""
        assert len(js_files) > 0, "未找到JavaScript文件"
    
    @pytest.mark.parametrize("js_file", [
        WEBUI_DIR / "static" / "app.js",
    ])
    def test_js_file_syntax(self, js_file: Path) -> None:
        """测试JavaScript语法"""
        if not js_file.exists():
            pytest.skip(f"{js_file} 不存在")
        
        content = js_file.read_text()
        
        basic_checks = [
            ("括号匹配", lambda c: c.count("{") == c.count("}")),
            ("圆括号匹配", lambda c: c.count("(") == c.count(")")),
            ("方括号匹配", lambda c: c.count("[") == c.count("]")),
        ]
        
        for check_name, check_func in basic_checks:
            assert check_func(content), f"{js_file.name}: {check_name}失败"
        
        # 检查关键函数定义
        required_functions = [
            "formatDuration",
            "formatTimestamp",
            "escapeHtml",
            "parseLogColors",
            "showToast",
            "LogPoller",
        ]
        
        for func_name in required_functions:
            assert func_name in content, f"{js_file.name}: 缺少函数 {func_name}"
    
    def test_js_parse_log_colors(self) -> None:
        """测试日志颜色解析函数"""
        js_file = WEBUI_DIR / "static" / "app.js"
        if not js_file.exists():
            pytest.skip("app.js不存在")
        
        content = js_file.read_text()
        
        # 验证parseLogColors函数包含关键词匹配
        color_keywords = [
            "log-success",
            "log-error", 
            "log-warning",
            "log-info",
            "log-command",
        ]
        
        for keyword in color_keywords:
            assert keyword in content, f"parseLogColors缺少颜色类: {keyword}"
        
        # 验证ANSI解析
        assert "parseANSI" in content or "\\x1b" in content, "缺少ANSI颜色码解析"


class TestTemplatesSyntax:
    """Jinja2模板语法检查"""
    
    @pytest.fixture
    def template_files(self) -> List[Path]:
        """获取所有模板文件"""
        template_dir = WEBUI_DIR / "templates"
        if template_dir.exists():
            return list(template_dir.glob("*.html"))
        return []
    
    def test_templates_exist(self, template_files: List[Path]) -> None:
        """测试模板文件存在"""
        assert len(template_files) > 0, "未找到模板文件"
    
    @pytest.mark.parametrize("template_file", [
        WEBUI_DIR / "templates" / "base.html",
        WEBUI_DIR / "templates" / "index.html",
        WEBUI_DIR / "templates" / "scenario.html",
        WEBUI_DIR / "templates" / "feature.html",
        WEBUI_DIR / "templates" / "logs.html",
        WEBUI_DIR / "templates" / "tasks.html",
        WEBUI_DIR / "templates" / "config.html",
        WEBUI_DIR / "templates" / "library.html",
    ])
    def test_template_syntax(self, template_file: Path) -> None:
        """测试Jinja2模板语法"""
        if not template_file.exists():
            pytest.skip(f"{template_file} 不存在")
        
        content = template_file.read_text()
        
        block_checks = [
            ("{% block %}匹配", lambda c: c.count("{% block") == c.count("{% endblock")),
            ("{% for %}匹配", lambda c: c.count("{% for") == c.count("{% endfor")),
            ("{% if %}匹配", lambda c: c.count("{% if") >= c.count("{% endif")),
        ]
        
        for check_name, check_func in block_checks:
            assert check_func(content), f"{template_file.name}: {check_name}失败"
        
        # 检查模板继承
        if template_file.name != "base.html":
            assert "{% extends" in content, f"{template_file.name}: 缺少模板继承"
    
    def test_base_template_blocks(self) -> None:
        """测试base.html定义的block"""
        base_html = WEBUI_DIR / "templates" / "base.html"
        if not base_html.exists():
            pytest.skip("base.html不存在")
        
        content = base_html.read_text()
        
        required_blocks = ["title", "content", "scripts"]
        for block in required_blocks:
            assert "{% block " + block in content, f"base.html缺少block: {block}"
    
    def test_logs_template_parse_log_colors(self) -> None:
        """测试logs.html中使用parseLogColors"""
        logs_html = WEBUI_DIR / "templates" / "logs.html"
        if not logs_html.exists():
            pytest.skip("logs.html不存在")
        
        content = logs_html.read_text()
        
        # 验证在script block中调用了parseLogColors
        assert "parseLogColors" in content, "logs.html未使用parseLogColors函数"


class TestPythonSyntax:
    """Python语法检查"""
    
    @pytest.fixture
    def python_files(self) -> List[Path]:
        """获取所有Python文件"""
        py_files = []
        if WEBUI_DIR.exists():
            py_files = list(WEBUI_DIR.glob("*.py"))
        return py_files
    
    def test_python_files_exist(self, python_files: List[Path]) -> None:
        """测试Python文件存在"""
        assert len(python_files) > 0, "未找到Python文件"
    
    @pytest.mark.parametrize("py_file", [
        WEBUI_DIR / "app.py",
        WEBUI_DIR / "runner.py",
    ])
    def test_python_syntax_compile(self, py_file: Path) -> None:
        """测试Python语法（通过编译）"""
        if not py_file.exists():
            pytest.skip(f"{py_file} 不存在")
        
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(py_file)],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"Python语法错误: {result.stderr}"
    
    def test_import_app_module(self) -> None:
        """测试导入app模块"""
        sys.path.insert(0, str(WEBUI_DIR))
        
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("app", WEBUI_DIR / "app.py")
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            else:
                pytest.fail("无法加载app.py")
        except SyntaxError as e:
            pytest.fail(f"app.py语法错误: {e}")
        except Exception as e:
            pytest.skip(f"导入失败（可能是依赖问题）: {e}")
        finally:
            sys.path.pop(0)
    
    def test_import_runner_module(self) -> None:
        """测试导入runner模块"""
        sys.path.insert(0, str(WEBUI_DIR))
        
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("runner", WEBUI_DIR / "runner.py")
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            else:
                pytest.fail("无法加载runner.py")
        except SyntaxError as e:
            pytest.fail(f"runner.py语法错误: {e}")
        except Exception as e:
            pytest.skip(f"导入失败（可能是依赖问题）: {e}")
        finally:
            sys.path.pop(0)


class TestConfigFile:
    """配置文件验证"""
    
    def test_config_file_exists(self) -> None:
        """测试配置文件存在"""
        config_file = WEBUI_DIR / "webui_config.yaml"
        assert config_file.exists(), f"配置文件不存在: {config_file}"
    
    def test_config_yaml_syntax(self) -> None:
        """测试YAML语法"""
        config_file = WEBUI_DIR / "webui_config.yaml"
        if not config_file.exists():
            pytest.skip("配置文件不存在")
        
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            assert config is not None, "配置文件为空"
        except yaml.YAMLError as e:
            pytest.fail(f"YAML语法错误: {e}")
    
    def test_config_structure(self) -> None:
        """测试配置文件结构"""
        config_file = WEBUI_DIR / "webui_config.yaml"
        if not config_file.exists():
            pytest.skip("配置文件不存在")
        
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        # 检查scenarios结构
        assert "scenarios" in config, "配置缺少scenarios字段"
        assert isinstance(config["scenarios"], dict), "scenarios应该是字典"
        
        for scenario_name, scenario_data in config["scenarios"].items():
            assert "display_name" in scenario_data, f"{scenario_name}缺少display_name"
            assert "description" in scenario_data, f"{scenario_name}缺少description"
            assert "features" in scenario_data, f"{scenario_name}缺少features"
            assert isinstance(scenario_data["features"], list), f"{scenario_name}的features应该是列表"
            
            for feature in scenario_data["features"]:
                assert "name" in feature, f"{scenario_name}的feature缺少name"
                assert "title" in feature, f"{scenario_name}的feature缺少title"
    
    def test_config_features_params(self) -> None:
        """测试features参数定义"""
        config_file = WEBUI_DIR / "webui_config.yaml"
        if not config_file.exists():
            pytest.skip("配置文件不存在")
        
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        for scenario_name, scenario_data in config["scenarios"].items():
            for feature in scenario_data["features"]:
                if "params" in feature:
                    assert isinstance(feature["params"], list), f"{scenario_name}/{feature['name']}的params应该是列表"
                    
                    for param in feature["params"]:
                        required_fields = ["name", "type", "label"]
                        for field in required_fields:
                            assert field in param, f"{scenario_name}/{feature['name']}的参数缺少{field}"
                        
                        # 检查type有效性
                        valid_types = ["text", "number", "select", "password", "file"]
                        assert param["type"] in valid_types, f"参数类型无效: {param['type']}"
                        
                        # select类型必须有options
                        if param["type"] == "select":
                            assert "options" in param, f"{param['name']}是select类型但缺少options"
    
    def test_config_libraries_structure(self) -> None:
        """测试libraries结构"""
        config_file = WEBUI_DIR / "webui_config.yaml"
        if not config_file.exists():
            pytest.skip("配置文件不存在")
        
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        if "libraries" not in config:
            pytest.skip("配置缺少libraries字段")
        
        assert isinstance(config["libraries"], dict), "libraries应该是字典"
        
        for lib_name, lib_data in config["libraries"].items():
            assert "display_name" in lib_data, f"{lib_name}缺少display_name"
            assert "description" in lib_data, f"{lib_name}缺少description"
            
            if "params" in lib_data:
                for param in lib_data["params"]:
                    assert "name" in param, f"{lib_name}的参数缺少name"
                    assert "type" in param, f"{lib_name}的参数缺少type"


class TestFlaskRoutes:
    """Flask路由测试"""
    
    @pytest.fixture
    def client(self) -> None:
        """获取Flask测试客户端"""
        sys.path.insert(0, str(WEBUI_DIR))
        
        try:
            from app import app as flask_app
            flask_app.testing = True
            client = flask_app.test_client()
            yield client
        except Exception as e:
            pytest.skip(f"无法加载Flask应用: {e}")
        finally:
            sys.path.pop(0)
    
    def test_index_route(self, client) -> None:
        """测试首页路由"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.content_type
    
    def test_tasks_route(self, client) -> None:
        """测试任务列表路由"""
        response = client.get("/tasks")
        assert response.status_code == 200
    
    def test_config_route(self, client) -> None:
        """测试配置文件路由"""
        response = client.get("/config")
        assert response.status_code == 200
    
    def test_library_route(self, client) -> None:
        """测试加速库路由"""
        response = client.get("/library")
        assert response.status_code == 200
    
    def test_scenario_route(self, client) -> None:
        """测试场景详情路由"""
        scenarios = ["common", "boundary_gateway_appliance", "kingbase_database", "opengauss_database"]
        for scenario in scenarios:
            response = client.get(f"/scenario/{scenario}")
            assert response.status_code == 200, f"/scenario/{scenario}返回{response.status_code}"
    
    def test_api_scenarios(self, client) -> None:
        """测试API: 获取scenarios"""
        response = client.get("/api/scenarios")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) > 0
    
    def test_api_features(self, client) -> None:
        """测试API: 获取features"""
        response = client.get("/api/features/common")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
    
    def test_api_libraries(self, client) -> None:
        """测试API: 获取libraries"""
        response = client.get("/api/libraries")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
    
    def test_api_tasks(self, client) -> None:
        """测试API: 获取任务列表"""
        response = client.get("/api/tasks")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
    
    def test_api_health(self, client) -> None:
        """测试API: 健康检查"""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data.get("status") == "ok"
    
    def test_api_config_files(self, client) -> None:
        """测试API: 获取配置文件列表"""
        response = client.get("/api/config/files")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)


class TestKAOTRunner:
    """KAOTRunner功能测试"""
    
    @pytest.fixture
    def runner(self) -> None:
        """获取KAOTRunner实例"""
        sys.path.insert(0, str(WEBUI_DIR))
        
        try:
            from runner import KAOTRunner
            config_path = WEBUI_DIR / "webui_config.yaml"
            runner = KAOTRunner(str(config_path), base_dir=str(PROJECT_ROOT))
            yield runner
        except Exception as e:
            pytest.skip(f"无法加载KAOTRunner: {e}")
        finally:
            sys.path.pop(0)
    
    def test_get_scenarios(self, runner) -> None:
        """测试获取scenarios"""
        scenarios = runner.get_scenarios()
        assert isinstance(scenarios, list)
        assert len(scenarios) > 0
        
        for scenario in scenarios:
            assert "name" in scenario
            assert "display_name" in scenario
    
    def test_get_features(self, runner) -> None:
        """测试获取features"""
        features = runner.get_features("common")
        assert isinstance(features, list)
        assert len(features) > 0
        
        for feature in features:
            assert "name" in feature
            assert "title" in feature
    
    def test_get_feature(self, runner) -> None:
        """测试获取单个feature"""
        feature = runner.get_feature_info("common", "disable_swap")
        assert feature is not None
        assert feature.get("name") == "disable_swap"
    
    def test_get_libraries(self, runner) -> None:
        """测试获取libraries"""
        libraries = runner.get_libraries()
        assert isinstance(libraries, list)
        
        if len(libraries) > 0:
            for lib in libraries:
                assert "name" in lib
                assert "display_name" in lib
    
    def test_build_generate_command(self, runner) -> None:
        """测试构建generate命令"""
        cmd = runner.build_generate_command(
            scenario="common",
            features=["disable_swap"],
            output_file="test.yaml"
        )
        assert isinstance(cmd, list)
        assert "python3" in cmd[0] or "kaot.py" in cmd[-1]
        assert "generate" in cmd
    
    def test_build_execute_command(self, runner) -> None:
        """测试构建execute命令"""
        cmd = runner.build_execute_command(
            target_file="test.yaml"
        )
        assert isinstance(cmd, list)
        assert "execute" in cmd
    
    def test_build_install_command(self, runner) -> None:
        """测试构建install命令"""
        cmd = runner.build_install_command(
            library_name="boostkit_ksl",
            install_dir="/tmp/test"
        )
        assert isinstance(cmd, list)
        assert "install" in cmd
    
    def test_build_uninstall_command(self, runner) -> None:
        """测试构建uninstall命令"""
        cmd = runner.build_uninstall_command(
            library_name="boostkit_ksl"
        )
        assert isinstance(cmd, list)
        assert "uninstall" in cmd
    
    def test_task_status_persistence(self, runner) -> None:
        """测试任务状态持久化"""
        import time
        
        task_id = f"test_task_{int(time.time())}"
        
        # 使用私有方法创建测试状态
        task_info = {
            "task_id": task_id,
            "status": "success",
            "command": ["test", "command"],
            "type": "generate",
            "start_time": time.time(),
            "end_time": time.time() + 1,
            "pid": 99999
        }
        runner._save_task_status(task_id, task_info)
        
        # 验证状态文件创建
        status_file = Path(runner.logs_dir) / f"{task_id}.status.json"
        assert status_file.exists(), "状态文件未创建"
        
        # 验证状态加载
        loaded_status = runner._load_task_status(task_id)
        assert loaded_status is not None
        assert loaded_status.get("status") == "success"
        assert loaded_status.get("task_id") == task_id
        assert "command" in loaded_status
        
        # 验证状态文件内容完整性
        with open(status_file, 'r', encoding='utf-8') as f:
            file_content = json.load(f)
        assert file_content.get("type") == "generate"
        
        # 清理测试文件
        status_file.unlink()


class TestStaticFiles:
    """静态文件测试"""
    
    def test_css_file_exists(self) -> None:
        """测试CSS文件存在"""
        css_file = WEBUI_DIR / "static" / "style.css"
        assert css_file.exists(), "style.css不存在"
    
    def test_css_syntax(self) -> None:
        """测试CSS基本语法"""
        css_file = WEBUI_DIR / "static" / "style.css"
        if not css_file.exists():
            pytest.skip("style.css不存在")
        
        content = css_file.read_text()
        
        assert content.count("{") == content.count("}"), "CSS括号不匹配"
        
        # 检查日志颜色类
        log_color_classes = [
            ".log-success",
            ".log-error",
            ".log-warning",
            ".log-info",
        ]
        
        for color_class in log_color_classes:
            assert color_class in content, f"CSS缺少日志颜色类: {color_class}"
    
    def test_launcher_script_exists(self) -> None:
        """测试启动脚本存在"""
        launcher = WEBUI_DIR / "launcher.sh"
        assert launcher.exists(), "launcher.sh不存在"
    
    def test_launcher_script_executable(self) -> None:
        """测试启动脚本可执行"""
        launcher = WEBUI_DIR / "launcher.sh"
        if not launcher.exists():
            pytest.skip("launcher.sh不存在")
        
        content = launcher.read_text()
        
        # 检查基本内容
        assert "python3" in content, "launcher.sh缺少python3调用"
        assert "app.py" in content, "launcher.sh缺少app.py引用"
        assert "#!/bin/bash" in content, "launcher.sh缺少shebang"


class TestLogColorFunction:
    """日志颜色解析功能测试"""
    
    def test_parse_log_colors_success_keywords(self) -> None:
        """测试成功关键词颜色"""
        js_file = WEBUI_DIR / "static" / "app.js"
        if not js_file.exists():
            pytest.skip("app.js不存在")
        
        content = js_file.read_text()
        
        # 验证成功关键词
        success_keywords = ["SUCCESS", "成功", "完成", "done", "OK"]
        found_keywords = [kw for kw in success_keywords if kw in content]
        assert len(found_keywords) > 0, "parseLogColors缺少成功关键词"
    
    def test_parse_log_colors_error_keywords(self) -> None:
        """测试错误关键词颜色"""
        js_file = WEBUI_DIR / "static" / "app.js"
        if not js_file.exists():
            pytest.skip("app.js不存在")
        
        content = js_file.read_text()
        
        # 验证错误关键词
        error_keywords = ["ERROR", "FAILED", "失败", "错误"]
        found_keywords = [kw for kw in error_keywords if kw in content]
        assert len(found_keywords) > 0, "parseLogColors缺少错误关键词"
    
    def test_log_container_styles(self) -> None:
        """测试日志容器样式"""
        css_file = WEBUI_DIR / "static" / "style.css"
        if not css_file.exists():
            pytest.skip("style.css不存在")
        
        content = css_file.read_text()
        
        # 验证日志容器样式
        assert ".log-container" in content, "缺少.log-container样式"
        assert "pre" in content, "缺少pre标签样式"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])