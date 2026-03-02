import React, { useState, useEffect } from 'react';
import './Dashboard.css'; 
import { useNavigate } from 'react-router-dom';
import { BACKEND_URL } from '../services/api';
import { 
    FaCar, 
    FaExclamationTriangle, 
    FaChartBar, 
    FaCheckCircle, 
    FaMoneyBillWave 
} from 'react-icons/fa';

const Dashboard = () => {
    const [stats, setStats] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);
    const navigate = useNavigate();

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const token = localStorage.getItem('token');
                if (!token) {
                    navigate('/login');
                    return;
                }

                const response = await fetch(`${BACKEND_URL}/dashboard-stats`, {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                    },
                });

                if (!response.ok) {
                    throw new Error('Failed to fetch dashboard stats');
                }

                const data = await response.json();
                setStats(data);
            } catch (err) {
                setError(err.message);
            } finally {
                setIsLoading(false);
            }
        };

        fetchStats();
    }, [navigate]);

    if (isLoading) {
        return <div className="vehicles-container loading-state">Loading Dashboard...</div>;
    }

    if (error) {
        return <div className="vehicles-container error-state">{error}</div>;
    }

    if (!stats) {
        return null;
    }

    return (
        <div className="vehicles-container"> 
            <div className="vehicles-header"> 
                <h2 className="vehicles-title">System Dashboard</h2> 
            </div>

            <div className="stat-grid">
                <div className="stat-box">
                    <div className="stat-icon vehicle">
                        <FaCar />
                    </div>
                    <div className="stat-info">
                        <h3>Total Vehicles</h3>
                        <p>{stats.total_vehicles || 0}</p>
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-icon violation">
                        <FaExclamationTriangle />
                    </div>
                    <div className="stat-info">
                        <h3>Total Violations</h3>
                        <p>{stats.total_violations || 0}</p>
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-icon top-violation">
                        <FaChartBar />
                    </div>
                    <div className="stat-info">
                        <h3>Most Common Violation</h3>
                        <p>{stats.top_violation || "N/A"}</p>
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-icon revenue">
                        <FaCheckCircle />
                    </div>
                    <div className="stat-info">
                        <h3>Total Revenue</h3>
                        {/* FIXED: Added fallback ( || 0 ) before calling .toFixed(2) */}
                        <p className="revenue">₹{(stats.total_paid || 0).toFixed(2)}</p>
                    </div>
                </div>
                <div className="stat-box">
                    <div className="stat-icon outstanding">
                        <FaMoneyBillWave />
                    </div>
                    <div className="stat-info">
                        <h3>Outstanding Fines</h3>
                        {/* FIXED: Added fallback ( || 0 ) before calling .toFixed(2) */}
                        <p className="outstanding">₹{(stats.total_unpaid || 0).toFixed(2)}</p>
                    </div>
                </div>
            </div>

        </div>
    );
};

export default Dashboard;