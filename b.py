@app.route('/api/reset-data', methods=['POST'])
def reset_data():
    """API d? xóa toàn b? d? li?u l?ch s?"""
    try:
        # T?o file r?ng d? xóa toàn b? d? li?u
        with open(DATA_FILE, 'w') as f:
            json.dump([], f)
        
        return jsonify({
            "status": "success", 
            "message": "Ðã xóa toàn b? d? li?u l?ch s? thành công"
        })
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"L?i khi xóa d? li?u: {str(e)}"
        }), 500

@app.route('/api/reset-config', methods=['POST'])
def reset_config():
    """API d? reset c?u hình v? m?c d?nh"""
    try:
        save_config(default_config)
        return jsonify({
            "status": "success", 
            "message": "Ðã reset c?u hình v? m?c d?nh",
            "config": default_config
        })
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"L?i khi reset c?u hình: {str(e)}"
        }), 500
