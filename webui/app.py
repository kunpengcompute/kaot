#!/usr/bin/env python3
"""
KAOT WebUI - Flask应用
提供可视化调优界面
"""

import os
import sys
import json
import argparse
import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for

script_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(script_dir)
sys.path.insert(0, script_dir)

from runner import KAOTRunner

app = Flask(__name__)
app.config['SECRET_KEY'] = 'kaot-webui-secret'


@app.template_filter('datetime')
def format_datetime(timestamp):
    if not timestamp:
        return '-'
    dt = datetime.datetime.fromtimestamp(timestamp)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


@app.template_filter('duration')
def format_duration(seconds):
    if not seconds:
        return '-'
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds / 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.0f}s"


config_path = os.path.join(script_dir, 'webui_config.yaml')
runner = KAOTRunner(config_path, base_dir=base_dir)


@app.route('/')
def index():
    scenarios = runner.get_scenarios()
    return render_template('index.html', scenarios=scenarios)


@app.route('/scenario/<name>')
def scenario_page(name):
    scenario_info = runner.get_scenario_info(name)
    if not scenario_info:
        return render_template('error.html', message='场景不存在')
    
    features = runner.get_features(name)
    return render_template('scenario.html', scenario=scenario_info, features=features)


@app.route('/feature/<scenario>/<feature_name>')
def feature_page(scenario, feature_name):
    feature_info = runner.get_feature_info(scenario, feature_name)
    if not feature_info:
        return render_template('error.html', message='调优项不存在')
    
    scenario_info = runner.get_scenario_info(scenario)
    return render_template('feature.html', feature=feature_info, scenario=scenario_info)


@app.route('/library')
def library_page():
    libraries = runner.get_libraries()
    return render_template('library.html', libraries=libraries)


@app.route('/library/<name>')
def library_detail_page(name):
    library_info = runner.get_library_info(name)
    if not library_info:
        return render_template('error.html', message='加速库不存在')
    return render_template('library_detail.html', library=library_info)


@app.route('/tasks')
def tasks_page():
    tasks = runner.get_all_tasks()
    return render_template('tasks.html', tasks=tasks)


@app.route('/logs/<task_id>')
def logs_page(task_id):
    task = runner.get_task_info(task_id)
    if not task:
        return render_template('error.html', message='任务不存在')
    return render_template('logs.html', task=task)


@app.route('/config')
def config_page():
    files = runner.get_config_files()
    return render_template('config.html', files=files)


@app.route('/config/<filename>')
def config_detail_page(filename):
    content = runner.get_config_content(filename)
    if content is None:
        return render_template('error.html', message='配置文件不存在')
    return render_template('config_detail.html', filename=filename, content=content)


@app.route('/error')
def error_page():
    message = request.args.get('message', '未知错误')
    return render_template('error.html', message=message)


@app.route('/api/scenarios')
def api_scenarios():
    return jsonify(runner.get_scenarios())


@app.route('/api/scenario/<name>')
def api_scenario(name):
    info = runner.get_scenario_info(name)
    if not info:
        return jsonify({'error': '场景不存在'}), 404
    return jsonify(info)


@app.route('/api/features/<scenario>')
def api_features(scenario):
    return jsonify(runner.get_features(scenario))


@app.route('/api/feature/<scenario>/<feature_name>')
def api_feature(scenario, feature_name):
    info = runner.get_feature_info(scenario, feature_name)
    if not info:
        return jsonify({'error': '调优项不存在'}), 404
    return jsonify(info)


@app.route('/api/generate', methods=['POST'])
def api_generate():
    data = request.json
    scenario = data.get('scenario')
    features = data.get('features', [])
    output_file = data.get('output_file', 'feature_config.yaml')
    configfile = data.get('configfile')
    
    if not scenario and not features:
        return jsonify({'error': '缺少scenario或features参数'}), 400
    
    try:
        result = runner.generate_config_async(scenario, features, output_file, configfile)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/execute', methods=['POST'])
def api_execute():
    data = request.json
    target_file = data.get('target_file')
    features = data.get('features', [])
    configfile = data.get('configfile')
    
    if not target_file:
        return jsonify({'error': '缺少target_file参数'}), 400
    
    try:
        result = runner.execute_config_async(target_file, features, configfile)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/basecfg', methods=['POST'])
def api_basecfg():
    data = request.json or {}
    configfile = data.get('configfile')
    
    try:
        result = runner.generate_basecfg_async(configfile)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/install', methods=['POST'])
def api_install():
    data = request.json
    library = data.get('library')
    install_dir = data.get('install_dir')
    
    if not library:
        return jsonify({'error': '缺少library参数'}), 400
    
    try:
        result = runner.install_library_async(library, install_dir)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/uninstall', methods=['POST'])
def api_uninstall():
    data = request.json
    library = data.get('library')
    
    if not library:
        return jsonify({'error': '缺少library参数'}), 400
    
    try:
        result = runner.uninstall_library_async(library)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/logs/<task_id>')
def api_logs(task_id):
    last_pos = int(request.args.get('pos', 0))
    result = runner.get_log_content(task_id, last_pos)
    return jsonify(result)


@app.route('/api/task/<task_id>')
def api_task(task_id):
    task = runner.get_task_info(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    return jsonify(task)


@app.route('/api/tasks')
def api_tasks():
    return jsonify(runner.get_all_tasks())


@app.route('/api/kill/<task_id>', methods=['POST'])
def api_kill(task_id):
    result = runner.kill_task(task_id)
    if result.get('success'):
        return jsonify(result)
    else:
        return jsonify(result), 400


@app.route('/api/retry/<task_id>', methods=['POST'])
def api_retry(task_id):
    result = runner.retry_task(task_id)
    if result.get('task_id'):
        return jsonify(result)
    else:
        return jsonify(result), 400


@app.route('/api/task/<task_id>/config')
def api_task_config(task_id):
    task = runner.get_task_info(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    
    params = task.get('params', {})
    output_file = params.get('output_file') or params.get('target_file')
    
    if not output_file:
        return jsonify({'error': '此任务无配置文件'}), 404
    
    content = runner.get_config_content(output_file)
    if content is None:
        return jsonify({'error': '配置文件不存在'}), 404
    
    return jsonify({'filename': output_file, 'content': content})


@app.route('/api/task/<task_id>/dbconfig')
def api_task_dbconfig(task_id):
    task = runner.get_task_info(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    
    params = task.get('params', {})
    configfile = params.get('configfile')
    
    if not configfile:
        if task.get('type') == 'execute':
            yaml_file = params.get('target_file')
            if yaml_file:
                configfile = runner.get_configfile_from_yaml(yaml_file)
        
        if not configfile:
            return jsonify({'error': '此任务无数据库配置文件'}), 404
    
    content = runner.get_database_config_content(configfile)
    if content is None:
        return jsonify({'error': '数据库配置文件不存在或无法读取'}), 404
    
    if ':' in configfile:
        _, file_path = configfile.split(':', 1)
    else:
        file_path = configfile
    
    return jsonify({'filename': file_path, 'configfile': configfile, 'content': content})


@app.route('/api/config/files')
def api_config_files():
    return jsonify(runner.get_config_files())


@app.route('/api/config/<filename>')
def api_config_content(filename):
    content = runner.get_config_content(filename)
    if content is None:
        return jsonify({'error': '文件不存在'}), 404
    return jsonify({'filename': filename, 'content': content})


@app.route('/api/config/<filename>', methods=['PUT'])
def api_config_save(filename):
    data = request.json
    content = data.get('content', '')
    result = runner.save_config_content(filename, content)
    if result.get('success'):
        return jsonify(result)
    else:
        return jsonify(result), 400


@app.route('/api/config/<filename>', methods=['DELETE'])
def api_config_delete(filename):
    result = runner.delete_config_file(filename)
    if result.get('success'):
        return jsonify(result)
    else:
        return jsonify(result), 400


@app.route('/api/libraries')
def api_libraries():
    return jsonify(runner.get_libraries())


@app.route('/api/library/<name>')
def api_library(name):
    info = runner.get_library_info(name)
    if not info:
        return jsonify({'error': '加速库不存在'}), 404
    return jsonify(info)


@app.route('/api/health')
def api_health():
    return jsonify({
        'status': 'ok',
        'timestamp': os.path.getmtime(config_path),
        'base_dir': base_dir
    })


def main():
    parser = argparse.ArgumentParser(description='KAOT WebUI')
    parser.add_argument('--port', type=int, default=8080, help='服务端口')
    parser.add_argument('--host', default='0.0.0.0', help='绑定地址')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    args = parser.parse_args()
    
    print(f"=== KAOT WebUI ===")
    print(f"启动端口: {args.port}")
    print(f"访问地址: http://{args.host if args.host != '0.0.0.0' else '本机IP'}:{args.port}")
    print(f"配置文件: {config_path}")
    print(f"基准目录: {base_dir}")
    print()
    
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == '__main__':
    main()