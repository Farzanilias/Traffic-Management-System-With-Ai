import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Login from '../components/Login';
import './LandingPage.css';

const LandingPage = ({ setIsAuthenticated }) => {
  const navigate = useNavigate();
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handleMouseMove = (event) => {
      const { clientX, clientY } = event;
      const x = (clientX / window.innerWidth - 0.5) * 2; 
      const y = (clientY / window.innerHeight - 0.5) * 2; 
      setMousePos({ x, y });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  const parallaxStyle = {
    transform: `translate(${mousePos.x * -20}px, ${mousePos.y * -20}px)`,
  };

  return (
    <div className="landing-container">
      <div className="blob blob-1"></div>
      <div className="blob blob-2"></div>
      <div className="blob blob-3"></div>

      <div className="landing-center-layout" style={parallaxStyle}>
        
        <div className="hero-content">
          <img src="/gov-logo.png" alt="Emblem" className="hero-logo floating-logo" />
          <h1 className="hero-title">SafeRide Command Center</h1>
          <h2 className="hero-subtitle">Intelligent AI Traffic Management</h2>
          <p className="hero-slogan">
            Efficient. Transparent. Secure. Towards a Safer City.
          </p>
        </div>

        <div className="hero-login-wrapper glass-panel">
          <Login setIsAuthenticated={setIsAuthenticated} />
        </div>

      </div>
    </div>
  );
};

export default LandingPage;