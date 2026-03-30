import React from 'react';
import './ProfessionalBackground.css';

const ProfessionalBackground = () => {
  return (
    <div className="professional-bg-container">
      {/* Gradient Background */}
      <div className="bg-gradient"></div>
      
      {/* Subtle Animated Accent Elements */}
      <div className="accent-orb accent-1"></div>
      <div className="accent-orb accent-2"></div>
      <div className="accent-orb accent-3"></div>
      
      {/* Grid Pattern Overlay (subtle) */}
      <div className="grid-overlay"></div>
      
      {/* Top accent bar */}
      <div className="accent-bar"></div>
    </div>
  );
};

export default ProfessionalBackground;
