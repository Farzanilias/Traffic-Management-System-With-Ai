import React, { useState, useRef } from 'react';
import './AutoDetect.css'; 
import { BACKEND_URL } from '../services/api';

const AutoDetect = () => {
    const [file, setFile] = useState(null);
    const [preview, setPreview] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(null);
    const [annotatedPreview, setAnnotatedPreview] = useState(null);
    const [detectedPlate, setDetectedPlate] = useState(null);
    const [videoURL, setVideoURL] = useState(null);
    const [isSampling, setIsSampling] = useState(false);
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const samplingRef = useRef(null);
    const SAMPLE_INTERVAL_MS = 1000; // sample every second by default

    const handleFileChange = (e) => {
        const selectedFile = e.target.files[0];
        setFile(selectedFile);
        setError(null);
        setSuccess(null);

        if (selectedFile) {
            const reader = new FileReader();
            reader.onloadend = () => {
                setPreview(reader.result);
            };
            reader.readAsDataURL(selectedFile);
        } else {
            setPreview(null);
        }
    };

    const handleVideoChange = (e) => {
        const file = e.target.files[0];
        if (file) {
            const url = URL.createObjectURL(file);
            setVideoURL(url);
            setAnnotatedPreview(null);
            setDetectedPlate(null);
        } else {
            setVideoURL(null);
        }
    };

    const startSampling = () => {
        if (!videoRef.current || !videoURL) return;
        if (isSampling) return;
        setIsSampling(true);
        videoRef.current.play().catch(() => {});
        samplingRef.current = setInterval(sampleFrame, SAMPLE_INTERVAL_MS);
    };

    const stopSampling = () => {
        if (samplingRef.current) {
            clearInterval(samplingRef.current);
            samplingRef.current = null;
        }
        if (videoRef.current) try { videoRef.current.pause(); } catch(e){}
        setIsSampling(false);
    };

    const sampleFrame = () => {
        const videoEl = videoRef.current;
        const canvas = canvasRef.current;
        if (!videoEl || !canvas) return;
        const ctx = canvas.getContext('2d');
        canvas.width = videoEl.videoWidth || 640;
        canvas.height = videoEl.videoHeight || 360;
        try {
            ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
            canvas.toBlob(async (blob) => {
                if (!blob) return;
                await sendFrameBlob(blob);
            }, 'image/jpeg', 0.8);
        } catch (e) {
            console.error('Frame sample error', e);
        }
    };

    const sendFrameBlob = async (blob) => {
        setIsLoading(true);
        setError(null);
        const formData = new FormData();
        const fileObj = new File([blob], 'frame.jpg', { type: 'image/jpeg' });
        formData.append('image_file', fileObj);
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`${BACKEND_URL}/autodetect`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData,
            });
            const data = await response.json();
            if (!response.ok) {
                console.warn('Frame detection failed', data);
                return;
            }
            if (data.annotated_image) setAnnotatedPreview(data.annotated_image);
            if (data.license_plate) setDetectedPlate(data.license_plate);
        } catch (err) {
            console.error(err);
        } finally {
            setIsLoading(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!file) {
            setError("Please select an image file first.");
            return;
        }

        setIsLoading(true);
        setError(null);
        setSuccess(null);

        const formData = new FormData();
        formData.append('image_file', file);

        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`${BACKEND_URL}/autodetect`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                },
                body: formData,
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || data.message || 'Detection failed');
            }
            setSuccess(data.message);
            if (data.annotated_image) {
                setAnnotatedPreview(data.annotated_image);
            }
            if (data.license_plate) {
                setDetectedPlate(data.license_plate);
            }

        } catch (err) {
            setError(err.message);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="autodetect-container">
            <h2 className="autodetect-title">Auto-Detect Violation</h2>
            <p className="autodetect-subtitle">Upload an image to detect 'No Helmet' violations.</p>

            <form onSubmit={handleSubmit} className="autodetect-form">
                <div className="form-group">
                    <label htmlFor="imageUpload" className="upload-label">
                        {preview ? "Change Image" : "Select Image"}
                    </label>
                    <input
                        id="imageUpload"
                        type="file"
                        accept="image/*"
                        onChange={handleFileChange}
                        className="upload-input"
                    />
                </div>

                <div className="form-group video-group">
                    <label htmlFor="videoUpload" className="upload-label">Upload Video (sample frames)</label>
                    <input id="videoUpload" type="file" accept="video/*" onChange={handleVideoChange} />
                    {videoURL && (
                        <div className="video-controls">
                            <video ref={videoRef} src={videoURL} style={{maxWidth: '100%'}} controls muted />
                            <div style={{marginTop:8}}>
                                <button type="button" onClick={startSampling} disabled={isSampling}>Start Sampling</button>
                                <button type="button" onClick={stopSampling} disabled={!isSampling}>Stop</button>
                            </div>
                        </div>
                    )}
                    <canvas ref={canvasRef} style={{display:'none'}} />
                </div>

                {preview && (
                    <div className="image-preview-container">
                        <img src={preview} alt="Selected" className="image-preview" />
                    </div>
                )}

                {annotatedPreview && (
                    <div className="annotated-preview-container">
                        <h4>Annotated Result</h4>
                        <img src={annotatedPreview} alt="Annotated" className="annotated-preview" />
                        {detectedPlate && <div className="detected-plate">Detected plate: {detectedPlate}</div>}
                    </div>
                )}

                <button
                    type="submit"
                    className={`autodetect-button ${isLoading ? 'disabled' : ''}`}
                    disabled={isLoading || !file}
                >
                    {isLoading ? "Analyzing..." : "Analyze Image"}
                </button>
            </form>

            {success && <div className="success-message">{success}</div>}
            {error && <div className="error-message">{error}</div>}
        </div>
    );
};

export default AutoDetect;