import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Header from './components/Header';
import Dashboard from './pages/Dashboard';
import Vehicles from './pages/Vehicles';
import Violations from './pages/Violations';
import Payments from './pages/Payments';
import RegisterVehicle from './pages/RegisterVehicle';
import AddViolation from './pages/AddViolation';
import LandingPage from './pages/LandingPage';
import AutoDetect from './pages/AutoDetect';
import MyProfile from './pages/MyProfile';

// Import our new 3D Background!
import CyberBackground from './components/CyberBackground'; 
import './App.css';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      setIsAuthenticated(true);
    }
  }, []);

  return (
    <Router>
      {/* THIS MAKES THE 3D GAME RUN ON EVERY PAGE */}
      <CyberBackground /> 

      {isAuthenticated && <Header setIsAuthenticated={setIsAuthenticated} />}
      <div className={isAuthenticated ? "main-content" : "landing-main"}>
        <Routes>
          <Route path="/" element={!isAuthenticated ? <LandingPage setIsAuthenticated={setIsAuthenticated} /> : <Navigate to="/dashboard" />} />
          <Route path="/dashboard" element={isAuthenticated ? <Dashboard /> : <Navigate to="/" />} />
          <Route path="/vehicles" element={isAuthenticated ? <Vehicles /> : <Navigate to="/" />} />
          <Route path="/violations" element={isAuthenticated ? <Violations /> : <Navigate to="/" />} />
          <Route path="/payments" element={isAuthenticated ? <Payments /> : <Navigate to="/" />} />
          <Route path="/register-vehicle" element={isAuthenticated ? <RegisterVehicle /> : <Navigate to="/" />} />
          <Route path="/add-violation" element={isAuthenticated ? <AddViolation /> : <Navigate to="/" />} />
          <Route path="/autodetect" element={isAuthenticated ? <AutoDetect /> : <Navigate to="/" />} />
          <Route path="/profile" element={isAuthenticated ? <MyProfile /> : <Navigate to="/" />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;