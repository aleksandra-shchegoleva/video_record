from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import json
from datetime import datetime
import logging
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация для локального сохранения
UPLOAD_FOLDER = 'video_interviews'
BASE_DIR = Path(__file__).parent
VIDEOS_DIR = BASE_DIR / UPLOAD_FOLDER

# Создаем папку для видео если её нет
VIDEOS_DIR.mkdir(exist_ok=True)

class LocalVideoStorage:
    def __init__(self, base_path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        logger.info(f"Инициализировано локальное хранилище: {self.base_path.absolute()}")
    
    def create_session_folder(self, session_id):
        """Создает папку для сессии"""
        current_date = datetime.now().strftime('%Y-%m-%d')
        session_folder = self.base_path / current_date / session_id
        session_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Создана папка для сессии: {session_folder}")
        return session_folder
    
    def save_video(self, video_data, session_id, question_number, question_text):
        """Сохраняет видео локально"""
        try:
            session_folder = self.create_session_folder(session_id)
            
            # Формируем имя файла
            timestamp = datetime.now().strftime('%H-%M-%S')
            filename = f'question_{question_number}_{timestamp}.webm'
            file_path = session_folder / filename
            
            # Сохраняем видео файл
            with open(file_path, 'wb') as f:
                f.write(video_data)
            
            # Сохраняем метаданные
            metadata = {
                'session_id': session_id,
                'question_number': int(question_number),
                'question_text': question_text,
                'filename': filename,
                'timestamp': datetime.now().isoformat(),
                'file_path': str(file_path.relative_to(self.base_path)),
                'file_size': len(video_data)
            }
            
            metadata_filename = f'question_{question_number}_metadata.json'
            metadata_path = session_folder / metadata_filename
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Видео сохранено: {file_path} ({len(video_data)} bytes)")
            return {
                'success': True,
                'file_path': str(file_path.relative_to(self.base_path)),
                'absolute_path': str(file_path),
                'metadata': metadata
            }
            
        except Exception as e:
            logger.error(f"Ошибка сохранения видео: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_session_info(self, session_id):
        """Получает информацию о сессии"""
        try:
            current_date = datetime.now().strftime('%Y-%m-%d')
            session_folder = self.base_path / current_date / session_id
            
            if not session_folder.exists():
                return {'success': False, 'error': 'Сессия не найдена'}
            
            video_files = list(session_folder.glob('*.webm'))
            metadata_files = list(session_folder.glob('*_metadata.json'))
            
            videos_info = []
            for video_file in video_files:
                file_info = {
                    'filename': video_file.name,
                    'size': video_file.stat().st_size,
                    'created': datetime.fromtimestamp(video_file.stat().st_ctime).isoformat()
                }
                videos_info.append(file_info)
            
            return {
                'success': True,
                'session_id': session_id,
                'total_questions': len(video_files),
                'session_folder': str(session_folder.relative_to(self.base_path)),
                'videos': videos_info
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения информации о сессии: {str(e)}")
            return {'success': False, 'error': str(e)}

# Инициализация локального хранилища
storage = LocalVideoStorage(VIDEOS_DIR)

@app.route('/')
def index():
    """Главная страница с HTML интерфейсом"""
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return """
        <h1>Файл index.html не найден</h1>
        <p>Убедитесь, что файл index.html находится в той же папке, что и app.py</p>
        """

@app.route('/upload-video', methods=['POST'])
def upload_video():
    """Обработка загрузки видео"""
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'Видео файл не найден'}), 400
        
        video_file = request.files['video']
        session_id = request.form.get('session_id', 'unknown')
        question_number = request.form.get('question_number', '1')
        question_text = request.form.get('question_text', '')
        
        if video_file.filename == '':
            return jsonify({'error': 'Файл не выбран'}), 400
        
        # Читаем данные файла
        video_data = video_file.read()
        
        if len(video_data) == 0:
            return jsonify({'error': 'Файл пустой'}), 400
        
        # Сохраняем локально
        result = storage.save_video(video_data, session_id, question_number, question_text)
        
        if result['success']:
            logger.info(f"Видео сохранено локально: {result['file_path']}")
            return jsonify({
                'success': True,
                'message': 'Видео успешно сохранено локально',
                'file_path': result['file_path'],
                'file_size': result['metadata']['file_size']
            })
        else:
            return jsonify({'error': f'Ошибка сохранения: {result["error"]}'}), 500
            
    except Exception as e:
        logger.error(f"Ошибка загрузки видео: {str(e)}")
        return jsonify({'error': f'Ошибка сервера: {str(e)}'}), 500

@app.route('/session-info/<session_id>')
def session_info(session_id):
    """Получение информации о сессии"""
    try:
        result = storage.get_session_info(session_id)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'error': result['error']}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/videos/<path:filename>')
def serve_video(filename):
    """Отдача видео файлов"""
    try:
        return send_from_directory(VIDEOS_DIR, filename)
    except Exception as e:
        logger.error(f"Ошибка отдачи файла {filename}: {str(e)}")
        return jsonify({'error': 'Файл не найден'}), 404

@app.route('/list-sessions')
def list_sessions():
    """Список всех сессий"""
    try:
        sessions = []
        if VIDEOS_DIR.exists():
            for date_folder in VIDEOS_DIR.iterdir():
                if date_folder.is_dir():
                    for session_folder in date_folder.iterdir():
                        if session_folder.is_dir():
                            video_count = len(list(session_folder.glob('*.webm')))
                            sessions.append({
                                'session_id': session_folder.name,
                                'date': date_folder.name,
                                'video_count': video_count,
                                'path': str(session_folder.relative_to(VIDEOS_DIR))
                            })
        
        return jsonify({
            'success': True,
            'sessions': sorted(sessions, key=lambda x: x['date'], reverse=True)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Проверка состояния сервиса"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    print("🚀 Запуск сервиса видео-интервью...")
    print(f"📁 Видео сохраняются в: {VIDEOS_DIR.absolute()}")
    print("✅ Сервис готов к работе!")
    print("🌐 Откройте http://localhost:5000 в браузере")
    print("📱 Для мобильных устройств используйте HTTPS")
    
    app.run(debug=True, host='0.0.0.0', port=5000)