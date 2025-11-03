# app/services/websocket_service.py
"""
WebSocket service for real-time communication
Import this in controllers to emit events
"""

# Import socketio from app.py
def get_socketio():
    """Get the socketio instance"""
    try:
        from app import socketio
        return socketio
    except ImportError:
        print("Warning: Could not import socketio from app")
        return None

# Create a proxy that can be imported
class SocketIOProxy:
    """Proxy class to access socketio instance"""
    
    @property
    def _socketio(self):
        return get_socketio()
    
    def emit(self, *args, **kwargs):
        """Emit an event"""
        socketio = self._socketio
        if socketio:
            return socketio.emit(*args, **kwargs)
        else:
            print(f"Warning: SocketIO not available, event not emitted: {args[0] if args else 'unknown'}")
    
    def send(self, *args, **kwargs):
        """Send a message"""
        socketio = self._socketio
        if socketio:
            return socketio.send(*args, **kwargs)
        else:
            print("Warning: SocketIO not available, message not sent")

# Create a singleton instance
socketio = SocketIOProxy()

# For backwards compatibility
__all__ = ['socketio']