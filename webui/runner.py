#!/usr/bin/env python3
"""
KAOT Runner - WebUI执行引擎
负责解析配置、构建命令、执行调优、管理日志
"""

import os
import sys
import yaml
import json
import time
import signal
import atexit
import datetime
import subprocess
import threading
import glob
from typing import Dict, List, Optional, Any
from pathlib import Path

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)


class KAOTRunner:
    """KAOT WebUI执行引擎"""
    
    def __init__(self, config_path: str, base_dir: str = None):
        self.config_path = config_path
        self.base_dir = base_dir or os.path.dirname(config_path)
        self.config = self._load_config()
        self.running_tasks: Dict[str, Dict] = {}
        self.task_counter = 0
        self._lock = threading.Lock()
        self._cleaning_up = False
        
        self.logs_dir = os.path.join(self.base_dir, "webui/logs")
        self.output_dir = os.path.join(self.base_dir, "output")
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        
        self._recover_tasks_on_startup()
        atexit.register(self._cleanup_on_exit)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _load_config(self) -> Dict:
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def get_scenarios(self) -> List[Dict]:
        scenarios = []
        for name, data in self.config.get('scenarios', {}).items():
            scenarios.append({
                'name': name,
                'display_name': data.get('display_name', name),
                'description': data.get('description', ''),
                'icon': data.get('icon', 'server'),
                'feature_count': len(data.get('features', [])),
                'requires_configfile': data.get('requires_configfile', False),
                'configfile_hint': data.get('configfile_hint', '')
            })
        return scenarios
    
    def get_scenario_info(self, scenario_name: str) -> Optional[Dict]:
        scenario = self.config.get('scenarios', {}).get(scenario_name)
        if not scenario:
            return None
        return {
            'name': scenario_name,
            'display_name': scenario.get('display_name', scenario_name),
            'description': scenario.get('description', ''),
            'icon': scenario.get('icon', 'server'),
            'requires_configfile': scenario.get('requires_configfile', False),
            'configfile_hint': scenario.get('configfile_hint', '')
        }
    
    def get_features(self, scenario_name: str) -> List[Dict]:
        scenario = self.config.get('scenarios', {}).get(scenario_name)
        if not scenario:
            return []
        
        features = []
        for feat in scenario.get('features', []):
            features.append({
                'name': feat.get('name'),
                'title': feat.get('title', feat.get('name')),
                'description': feat.get('description', ''),
                'needs_reboot': feat.get('needs_reboot', False),
                'has_params': len(feat.get('params', [])) > 0
            })
        return features
    
    def get_feature_info(self, scenario_name: str, feature_name: str) -> Optional[Dict]:
        scenario = self.config.get('scenarios', {}).get(scenario_name)
        if not scenario:
            return None
        
        for feat in scenario.get('features', []):
            if feat.get('name') == feature_name:
                params_info = []
                
                for param in feat.get('params', []):
                    param_info = {
                        'name': param.get('name'),
                        'type': param.get('type', 'text'),
                        'label': param.get('label', param.get('name')),
                        'required': param.get('required', False),
                        'default': param.get('default', ''),
                        'placeholder': param.get('placeholder', ''),
                        'description': param.get('description', '')
                    }
                    if param.get('type') == 'select':
                        param_info['options'] = param.get('options', [])
                    if param.get('type') == 'number':
                        param_info['min'] = param.get('min')
                        param_info['max'] = param.get('max')
                    params_info.append(param_info)
                
                return {
                    'name': feature_name,
                    'title': feat.get('title', feature_name),
                    'description': feat.get('description', ''),
                    'needs_reboot': feat.get('needs_reboot', False),
                    'params': params_info,
                    'scenario': scenario_name
                }
        return None
    
    def get_database_config_content(self, configfile: str) -> Optional[str]:
        if not configfile:
            return None
        
        if ':' in configfile:
            _, file_path = configfile.split(':', 1)
        else:
            file_path = configfile
        
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"读取数据库配置文件失败: {e}")
            return None
    
    def get_configfile_from_yaml(self, yaml_file: str) -> Optional[str]:
        full_path = os.path.join(self.output_dir, yaml_file)
        if not os.path.exists(full_path):
            return None
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
            
            if not content:
                return None
            
            optimization_items = content.get('OPTIMIZATION_ITEMS', [])
            for item in optimization_items:
                config_path = item.get('config_path')
                config_mapping_apps_name = item.get('config_mapping_apps_name')
                if config_path and config_mapping_apps_name:
                    return f"{config_mapping_apps_name}:{config_path}"
                elif config_path:
                    return config_path
            
            return None
        except Exception as e:
            print(f"从配置文件提取数据库路径失败: {e}")
            return None
    
    def get_libraries(self) -> List[Dict]:
        libraries = []
        for name, data in self.config.get('libraries', {}).items():
            libraries.append({
                'name': name,
                'display_name': data.get('display_name', name),
                'description': data.get('description', ''),
                'manual_download': data.get('manual_download', False),
                'download_url': data.get('download_url', '')
            })
        return libraries
    
    def get_library_info(self, library_name: str) -> Optional[Dict]:
        lib = self.config.get('libraries', {}).get(library_name)
        if not lib:
            return None
        
        params_info = []
        for param in lib.get('params', []):
            param_info = {
                'name': param.get('name'),
                'type': param.get('type', 'text'),
                'label': param.get('label', param.get('name')),
                'required': param.get('required', False),
                'default': param.get('default', ''),
                'placeholder': param.get('placeholder', ''),
                'description': param.get('description', '')
            }
            params_info.append(param_info)
        
        return {
            'name': library_name,
            'display_name': lib.get('display_name', library_name),
            'description': lib.get('description', ''),
            'manual_download': lib.get('manual_download', False),
            'download_url': lib.get('download_url', ''),
            'params': params_info
        }
    
    def generate_task_id(self) -> str:
        with self._lock:
            self.task_counter += 1
            return f"task_{int(time.time())}_{self.task_counter}"
    
    def build_generate_command(self, scenario: str, features: List[str], 
                                output_file: str, configfile: str = None) -> List[str]:
        cmd = ['python3', os.path.join(self.base_dir, 'kaot.py'), 'generate']
        
        if features:
            cmd.extend(['-f', ','.join(features)])
        elif scenario:
            cmd.extend(['-s', scenario])
        
        cmd.extend(['-o', output_file])
        
        if configfile:
            cmd.extend(['--configfile', configfile])
        
        cmd.extend(['-l', 'debug'])
        return cmd
    
    def build_execute_command(self, target_file: str, features: List[str] = None,
                               configfile: str = None) -> List[str]:
        cmd = ['python3', os.path.join(self.base_dir, 'kaot.py'), 'execute']
        cmd.extend(['-tp', target_file])
        
        if features:
            cmd.extend(['-f', ','.join(features)])
        
        if configfile:
            cmd.extend(['--configfile', configfile])
        
        cmd.extend(['-l', 'debug'])
        return cmd
    
    def build_install_command(self, library_name: str, install_dir: str = None) -> List[str]:
        cmd = ['python3', os.path.join(self.base_dir, 'kaot.py'), 'install']
        cmd.extend(['-n', library_name])
        
        if install_dir:
            cmd.extend(['-d', install_dir])
        
        cmd.extend(['-l', 'debug'])
        return cmd
    
    def build_uninstall_command(self, library_name: str) -> List[str]:
        cmd = ['python3', os.path.join(self.base_dir, 'kaot.py'), 'uninstall']
        cmd.extend(['-n', library_name])
        cmd.extend(['-l', 'debug'])
        return cmd
    
    def build_basecfg_command(self, configfile: str = None) -> List[str]:
        cmd = ['python3', os.path.join(self.base_dir, 'kaot.py'), 'basecfg']
        if configfile:
            cmd.extend(['--configfile', configfile])
        cmd.extend(['-l', 'debug'])
        return cmd
    
    def execute_async(self, task_type: str, cmd: List[str], 
                      params: Dict = None) -> Dict:
        task_id = self.generate_task_id()
        log_file = os.path.join(self.logs_dir, f"{task_id}.log")
        
        task_info = {
            'task_id': task_id,
            'type': task_type,
            'status': 'running',
            'start_time': time.time(),
            'log_file': log_file,
            'command': ' '.join(cmd),
            'pid': None,
            'params': params or {}
        }
        
        def run_process():
            try:
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(f"=== 任务开始: {task_id} ===\n")
                    f.write(f"类型: {task_type}\n")
                    f.write(f"命令: {' '.join(cmd)}\n")
                    f.write("=" * 50 + "\n\n")
                    f.flush()
                    
                    proc = subprocess.Popen(
                        cmd,
                        stdout=f,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.PIPE,
                        bufsize=0,
                        cwd=self.base_dir,
                        start_new_session=True
                    )
                    
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass
                    
                    with self._lock:
                        task_info['pid'] = proc.pid
                    
                    self._save_task_status(task_id, task_info)
                    
                    proc.wait()
                    
                    with self._lock:
                        task_info['status'] = 'success' if proc.returncode == 0 else 'failed'
                        task_info['end_time'] = time.time()
                        task_info['returncode'] = proc.returncode
                    
                    self._save_task_status(task_id, task_info)
                    
                    with open(log_file, 'a', encoding='utf-8') as f_append:
                        f_append.write("\n" + "=" * 50 + "\n")
                        f_append.write(f"=== 任务结束: {task_id} ===\n")
                        f_append.write(f"状态: {task_info['status']}\n")
                        f_append.write(f"返回码: {proc.returncode}\n")
                        f_append.write(f"耗时: {task_info['end_time'] - task_info['start_time']:.2f}s\n")
            
            except Exception as e:
                with self._lock:
                    task_info['status'] = 'error'
                    task_info['error'] = str(e)
                    task_info['end_time'] = time.time()
                
                self._save_task_status(task_id, task_info)
                
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n错误: {e}\n")
        
        thread = threading.Thread(target=run_process, daemon=True)
        thread.start()
        
        with self._lock:
            self.running_tasks[task_id] = task_info
        
        return {
            'task_id': task_id,
            'status': 'started',
            'message': f'任务 {task_id} 已启动'
        }
    
    def generate_config_async(self, scenario: str, features: List[str], 
                               output_file: str, configfile: str = None) -> Dict:
        cmd = self.build_generate_command(scenario, features, output_file, configfile)
        return self.execute_async('generate', cmd, {
            'scenario': scenario,
            'features': features,
            'output_file': output_file,
            'configfile': configfile
        })
    
    def execute_config_async(self, target_file: str, features: List[str] = None,
                              configfile: str = None) -> Dict:
        cmd = self.build_execute_command(target_file, features, configfile)
        return self.execute_async('execute', cmd, {
            'target_file': target_file,
            'features': features,
            'configfile': configfile
        })
    
    def install_library_async(self, library_name: str, install_dir: str = None) -> Dict:
        cmd = self.build_install_command(library_name, install_dir)
        return self.execute_async('install', cmd, {
            'library': library_name,
            'install_dir': install_dir
        })
    
    def uninstall_library_async(self, library_name: str) -> Dict:
        cmd = self.build_uninstall_command(library_name)
        return self.execute_async('uninstall', cmd, {
            'library': library_name
        })
    
    def generate_basecfg_async(self, configfile: str = None) -> Dict:
        cmd = self.build_basecfg_command(configfile)
        return self.execute_async('basecfg', cmd, {
            'configfile': configfile
        })
    
    def get_task_info(self, task_id: str) -> Optional[Dict]:
        with self._lock:
            return self.running_tasks.get(task_id)
    
    def get_log_content(self, task_id: str, last_pos: int = 0) -> Dict:
        task = self.get_task_info(task_id)
        if not task:
            return {'content': '', 'pos': 0, 'status': 'unknown'}
        
        log_file = task.get('log_file')
        if not log_file or not os.path.exists(log_file):
            return {'content': '', 'pos': 0, 'status': task.get('status', 'unknown')}
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                f.seek(last_pos)
                content = f.read()
                new_pos = f.tell()
            
            return {
                'content': content,
                'pos': new_pos,
                'status': task.get('status', 'running')
            }
        except Exception as e:
            return {'content': '', 'pos': last_pos, 'status': 'error', 'error': str(e)}
    
    def get_all_tasks(self) -> List[Dict]:
        with self._lock:
            return list(self.running_tasks.values())
    
    def kill_task(self, task_id: str) -> Dict:
        task = self.get_task_info(task_id)
        if not task:
            return {'success': False, 'error': '任务不存在'}
        
        if task.get('status') != 'running':
            return {'success': False, 'error': f'任务状态为 {task.get("status")}，无法中止'}
        
        pid = task.get('pid')
        if not pid:
            return {'success': False, 'error': '无法获取进程PID'}
        
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.3)
            
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            
            with self._lock:
                task['status'] = 'killed'
                task['end_time'] = time.time()
            
            self._save_task_status(task_id, task)
            
            log_file = task.get('log_file')
            if log_file and os.path.exists(log_file):
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write("\n" + "=" * 50 + "\n")
                    f.write(f"=== 任务被中止: {task_id} ===\n")
                    f.write(f"中止时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            return {'success': True, 'message': '任务已中止'}
        
        except ProcessLookupError:
            with self._lock:
                task['status'] = 'killed'
                task['end_time'] = time.time()
            self._save_task_status(task_id, task)
            return {'success': True, 'message': '进程已不存在'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def retry_task(self, task_id: str) -> Dict:
        task = self.get_task_info(task_id)
        if not task:
            return {'success': False, 'error': '任务不存在'}
        
        if task.get('status') not in ['failed', 'error', 'killed']:
            return {'success': False, 'error': f'任务状态为 {task.get("status")}，无法重试'}
        
        task_type = task.get('type')
        params = task.get('params', {})
        
        if task_type == 'generate':
            return self.generate_config_async(
                params.get('scenario'),
                params.get('features', []),
                params.get('output_file', 'feature_config.yaml'),
                params.get('configfile')
            )
        elif task_type == 'execute':
            return self.execute_config_async(
                params.get('target_file'),
                params.get('features'),
                params.get('configfile')
            )
        elif task_type == 'install':
            return self.install_library_async(
                params.get('library'),
                params.get('install_dir')
            )
        elif task_type == 'uninstall':
            return self.uninstall_library_async(
                params.get('library')
            )
        elif task_type == 'basecfg':
            return self.generate_basecfg_async(
                params.get('configfile')
            )
        else:
            return {'success': False, 'error': f'未知任务类型: {task_type}'}
    
    def get_config_files(self) -> List[Dict]:
        files = []
        if not os.path.exists(self.output_dir):
            return files
        
        for f in os.listdir(self.output_dir):
            if f.endswith('.yaml') or f.endswith('.yml'):
                full_path = os.path.join(self.output_dir, f)
                stat = os.stat(full_path)
                files.append({
                    'name': f,
                    'path': full_path,
                    'size': stat.st_size,
                    'modified': stat.st_mtime
                })
        return sorted(files, key=lambda x: x['modified'], reverse=True)
    
    def get_config_content(self, filename: str) -> Optional[str]:
        full_path = os.path.join(self.output_dir, filename)
        if not os.path.exists(full_path):
            return None
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return None
    
    def save_config_content(self, filename: str, content: str) -> Dict:
        full_path = os.path.join(self.output_dir, filename)
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {'success': True, 'message': f'配置文件 {filename} 已保存'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def delete_config_file(self, filename: str) -> Dict:
        full_path = os.path.join(self.output_dir, filename)
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
                return {'success': True, 'message': f'配置文件 {filename} 已删除'}
            return {'success': False, 'error': '文件不存在'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _save_task_status(self, task_id: str, task_info: Dict):
        status_file = os.path.join(self.logs_dir, f"{task_id}.status.json")
        try:
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(task_info, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存任务状态失败: {e}")
    
    def _load_task_status(self, task_id: str) -> Optional[Dict]:
        status_file = os.path.join(self.logs_dir, f"{task_id}.status.json")
        if not os.path.exists(status_file):
            return None
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载任务状态失败: {e}")
            return None
    
    def _is_process_alive(self, pid: int) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
    
    def _recover_tasks_on_startup(self):
        status_files = glob.glob(os.path.join(self.logs_dir, "*.status.json"))
        
        for status_file in status_files:
            task_id = os.path.basename(status_file).replace('.status.json', '')
            
            try:
                with open(status_file, 'r', encoding='utf-8') as f:
                    task = json.load(f)
            except (json.JSONDecodeError, IOError, OSError):
                continue
            
            status = task.get('status')
            pid = task.get('pid')
            
            if status == 'running':
                if self._is_process_alive(pid):
                    print(f"恢复运行中的任务: {task_id} (PID: {pid})")
                    with self._lock:
                        self.running_tasks[task_id] = task
                        self.task_counter += 1
                else:
                    print(f"任务 {task_id} 进程已终止，更新状态")
                    task['status'] = 'failed'
                    task['end_time'] = time.time()
                    task['reason'] = '进程意外终止'
                    self._save_task_status(task_id, task)
                    
                    log_file = task.get('log_file')
                    if log_file and os.path.exists(log_file):
                        with open(log_file, 'a', encoding='utf-8') as f:
                            f.write("\n" + "=" * 50 + "\n")
                            f.write(f"=== 进程意外终止 (WebUI重启时检测) ===\n")
                            f.write(f"检测时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            elif status in ['success', 'failed', 'error', 'killed']:
                age_hours = (time.time() - task.get('end_time', task.get('start_time', 0))) / 3600
                if age_hours < 24:
                    with self._lock:
                        self.running_tasks[task_id] = task
    
    def _cleanup_on_exit(self):
        if self._cleaning_up:
            return
        
        self._cleaning_up = True
        print("\n正在清理运行中的任务...")
        
        with self._lock:
            running = [(tid, t) for tid, t in self.running_tasks.items()
                       if t.get('status') == 'running']
        
        for task_id, task in running:
            pid = task.get('pid')
            if pid and self._is_process_alive(pid):
                print(f"终止任务 {task_id} (PID: {pid})")
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.3)
                    if self._is_process_alive(pid):
                        os.kill(pid, signal.SIGKILL)
                except Exception as e:
                    print(f"终止任务 {task_id} 失败: {e}")
                
                task['status'] = 'killed'
                task['end_time'] = time.time()
                task['reason'] = 'WebUI退出时终止'
                self._save_task_status(task_id, task)
                
                log_file = task.get('log_file')
                if log_file and os.path.exists(log_file):
                    try:
                        with open(log_file, 'a', encoding='utf-8') as f:
                            f.write("\n" + "=" * 50 + "\n")
                            f.write(f"=== 任务因WebUI退出而终止 ===\n")
                            f.write(f"终止时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    except (IOError, OSError):
                        pass
        
        print("清理完成")
    
    def _signal_handler(self, signum, frame):
        if self._cleaning_up:
            return
        
        print(f"\n收到信号 {signum}，正在退出...")
        self._cleanup_on_exit()
        sys.exit(0)