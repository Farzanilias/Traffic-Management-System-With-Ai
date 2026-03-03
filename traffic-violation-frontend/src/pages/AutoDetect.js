import React, { useState } from 'react';
import './AutoDetect.css'; 
import { BACKEND_URL } from '../services/api';

const AutoDetect = () => {
    // Media States
    const [imageFile, setImageFile] = useState(null);
    const [videoFile, setVideoFile] = useState(null);
    const [imagePreview, setImagePreview] = useState(null);
    const [videoPreviewURL, setVideoPreviewURL] = useState(null);
    
    // Process States
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(null);
    
    // Result States
    const [annotatedImg, setAnnotatedImg] = useState(null);
    const [processedVid, setProcessedVid] = useState(null);
    const [detectedPlate, setDetectedPlate] = useState(null);

    const handleImageChange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        setImageFile(file);
        setVideoFile(null); 
        setVideoPreviewURL(null); 
        resetResults();
        
        const reader = new FileReader();
        reader.onloadend = () => setImagePreview(reader.result);
        reader.readAsDataURL(file);
    };

    const handleVideoChange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        setVideoFile(file);
        setImageFile(null); 
        setImagePreview(null); 
        resetResults();
        
        setVideoPreviewURL(URL.createObjectURL(file));
    };

    const resetResults = () => {
        setError(null); 
        setSuccess(null); 
        setAnnotatedImg(null); 
        setProcessedVid(null); 
        setDetectedPlate(null);
    };

    const handleImageSubmit = async (e) => {
        e.preventDefault();
        if (!imageFile) return;
        
        setIsLoading(true);
        resetResults();
        
        const formData = new FormData();
        formData.append('image_file', imageFile);

        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`${BACKEND_URL}/autodetect`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData,
            });
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.error || 'Detection failed');
            
            setSuccess(data.message);
            if (data.annotated_image) setAnnotatedImg(data.annotated_image);
            if (data.license_plate) setDetectedPlate(data.license_plate);
        } catch (err) {
            setError(err.message);
        } finally {
            setIsLoading(false);
        }
    };

    const handleVideoSubmit = async () => {
        if (!videoFile) return;
        
        setIsLoading(true);
        resetResults();
        
        const formData = new FormData();
        formData.append('video_file', videoFile);

        try {
            const token = localStorage.getItem('token');
            // Calls the new continuous video processing route!
            const response = await fetch(`${BACKEND_URL}/autodetect-video`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData,
            });
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.error || 'Video processing failed');
            
            setSuccess(data.message);
            if (data.annotated_image) setAnnotatedImg(data.annotated_image);
            if (data.license_plate) setDetectedPlate(data.license_plate);
            if (data.video_url) {
                // Use the video_url from response (preferred)
                setProcessedVid(`${BACKEND_URL}${data.video_url}`);
            } else if (data.video_filename) {
                // Fallback to constructing the URL
                setProcessedVid(`${BACKEND_URL}/evidence/${data.video_filename}`);
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="autodetect-container">
            <h2 className="section-title">SafeRide AI Command Center</h2>
            
            <div className="autodetect-form glass-panel">
                
                {/* --- IMAGE UPLOAD SECTION --- */}
                <div className="form-group align-center">
                    <label className="label-title">Photo Analysis</label>
                    <label htmlFor="imgInp" className="upload-label">
                        {imageFile ? "Image Loaded - Click to Change" : "Upload Evidence Photo"}
                    </label>
                    <input id="imgInp" type="file" accept="image/*" onChange={handleImageChange} className="upload-input" />
                    
                    {imagePreview && (
                        <div className="image-preview-container" style={{marginTop: '15px'}}>
                            <img src={imagePreview} className="image-preview" alt="Input" style={{maxWidth: '100%', borderRadius: '8px'}} />
                        </div>
                    )}
                    
                    {imageFile && (
                        <button onClick={handleImageSubmit} className={`autodetect-button ${isLoading ? 'disabled' : ''}`} disabled={isLoading} style={{marginTop: '15px', width: '100%'}}>
                            {isLoading ? "Scanning Image..." : "Analyze Photo"}
                        </button>
                    )}
                </div>

                <hr style={{margin: '30px 0', borderColor: 'rgba(255,255,255,0.1)'}} />

                {/* --- VIDEO UPLOAD SECTION --- */}
                <div className="form-group align-center video-group">
                    <label className="label-title">Continuous Video Enforcement</label>
                    <label htmlFor="vidInp" className="upload-label">
                        {videoFile ? "Video Loaded - Click to Change" : "Upload Traffic Clip (.mp4)"}
                    </label>
                    <input id="vidInp" type="file" accept="video/*" onChange={handleVideoChange} className="upload-input" />
                    
                    {videoPreviewURL && !processedVid && (
                        <div className="video-controls" style={{marginTop: '15px'}}>
                            <video src={videoPreviewURL} style={{maxWidth: '100%', borderRadius: '12px'}} controls muted />
                        </div>
                    )}
                    
                    {videoFile && (
                        <button onClick={handleVideoSubmit} className={`autodetect-button ${isLoading ? 'disabled' : ''}`} disabled={isLoading} style={{marginTop: '15px', width: '100%', backgroundColor: '#2196F3'}}>
                            {isLoading ? "Processing Full Video (Please Wait)..." : "Analyze Full Video"}
                        </button>
                    )}
                </div>
                
                {/* --- STATUS MESSAGES --- */}
                {isLoading && <div className="loading-state" style={{marginTop: '20px', color: '#00f3ff', textAlign: 'center'}}>AI Engines processing data. This may take a moment depending on file size...</div>}
                {success && <div className="success-message" style={{marginTop: '20px', textAlign: 'center'}}>{success}</div>}
                {error && <div className="error-message" style={{marginTop: '20px', textAlign: 'center'}}>{error}</div>}

                {/* --- MASTER RESULTS VIEW --- */}
                {(annotatedImg || processedVid) && (
                    <div className="annotated-preview-container" style={{marginTop: '30px', paddingTop: '20px', borderTop: '1px solid rgba(255,255,255,0.1)'}}>
                        <h3 style={{color: '#00f3ff', marginBottom: '15px', textAlign: 'center'}}>AI Evidence Report</h3>
                        
                        {detectedPlate && (
                            <div className="detected-plate" style={{color: '#00ff00', marginBottom: '20px', fontSize: '22px', fontWeight: 'bold', backgroundColor: 'rgba(0,0,0,0.7)', padding: '15px', borderRadius: '8px', textAlign: 'center', border: '1px solid #00ff00'}}>
                                PLATE DETECTED: {detectedPlate}
                            </div>
                        )}

                        <div style={{display: 'flex', flexDirection: 'column', gap: '20px'}}>
                            {/* Show the best extracted frame */}
                            {annotatedImg && (
                                <div>
                                    <p style={{color: '#aaa', marginBottom: '5px'}}>High-Clarity Capture (API Sent)</p>
                                    <img src={annotatedImg} alt="AI Result" style={{maxWidth: '100%', borderRadius: '12px', border: '2px solid #00f3ff'}} />
                                </div>
                            )}

                            {/* Show the fully processed continuous video */}
                            {processedVid && (
                                <div>
                                    <p style={{color: '#aaa', marginBottom: '5px'}}>Continuous Tracking Feed</p>
                                    <video src={processedVid} style={{maxWidth: '100%', borderRadius: '12px', border: '2px solid #ff9800'}} controls autoPlay loop muted />
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default AutoDetect;