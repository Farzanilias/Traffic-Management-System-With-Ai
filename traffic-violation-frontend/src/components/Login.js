import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './Login.css';
import { BACKEND_URL } from '../services/api';

const Login = ({ setIsAuthenticated }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    
    try {
      const response = await fetch(`${BACKEND_URL}/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();

      if (response.ok) {
        localStorage.setItem('token', data.token);
        localStorage.setItem('role', data.role);
        setIsAuthenticated(true);
        navigate('/dashboard'); 
      } else {
        setError(data.message || 'Access Denied: Invalid Credentials');
      }
    } catch (err) {
      setError('Connection Error: System Offline');
      console.error('Login error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-container">
      <h2 className="login-title">System Access</h2>
      
      {error && <div className="error-message">{error}</div>}
      
      <form className="login-form" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Admin ID / Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          disabled={isLoading}
        />
        <input
          type="password"
          placeholder="Passcode"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          disabled={isLoading}
        />
        <button type="submit" className="login-button" disabled={isLoading}>
          {isLoading ? 'Authenticating...' : 'Initialize'}
        </button>
      </form>
    </div>
  );
};

export default Login;