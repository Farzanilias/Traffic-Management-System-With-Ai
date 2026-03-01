import React from 'react';
import Login from '../components/Login';
import './LandingPage.css';

const LandingPage = ({ setIsAuthenticated }) => {
  return (
    <div className="landing-container">
      {/* The Main Content */}
      <div className="landing-center-layout">
        <div className="hero-content">
          <img src="/gov-logo.png" alt="Emblem" className="hero-logo" />
          <h1 className="hero-title">SafeRide Command Center</h1>
          <h2 className="hero-subtitle">Intelligent AI Traffic Management</h2>
          <p className="hero-slogan">
            Efficient. Transparent. Secure. Towards a Safer City.
          </p>
        </div>

        <div className="hero-login-wrapper">
          <Login setIsAuthenticated={setIsAuthenticated} />
        </div>
      </div>
    </div>
  );
};

export default LandingPage;