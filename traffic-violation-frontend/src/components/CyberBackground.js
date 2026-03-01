import React from 'react';
import './CyberBackground.css';

const CyberBackground = () => {
  return (
    <div className="cyber-container">
      <div className="cyber-scene">
        {/* The 3D Moving Highway Grid */}
        <div className="cyber-floor"></div>
        
        {/* 3D Obstacle Cars */}
        <div className="cyber-car car-a">🏎️</div>
        <div className="cyber-car car-b">🚓</div>
        <div className="cyber-car car-c">🚕</div>
        
        {/* The 3D Player Bike */}
        <div className="cyber-bike">🏍️</div>
      </div>
      
      {/* Dark gradient to blend the edges */}
      <div className="cyber-overlay"></div>
    </div>
  );
};

export default CyberBackground;