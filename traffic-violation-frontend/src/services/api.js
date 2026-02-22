import axios from "axios";

const API_URL = process.env.REACT_APP_BACKEND_URL || "http://127.0.0.1:5000"; // Flask Backend URL (env override)

export const BACKEND_URL = API_URL;

// Set up axios instance with default headers
const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Add request interceptor to include the token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const getVehicles = async () => {
  return await api.get("/get-vehicles");
};

export const getViolations = async (licensePlate) => {
  return await api.get(`/get-violations/${licensePlate}`);
};

export const getViolationDetails = async (violationID) => {
  const res = await api.get(`/get-violation/${violationID}`);
  return res.data;
};
export const payFine = async (violationID, paymentMethod, paymentDetails = null) => {
  const payload = {
    PaymentMethod: paymentMethod,
  };

  // Include payment details if provided (for credit card payments)
  if (paymentMethod === "Credit Card" && paymentDetails) {
    payload.PaymentDetails = {
      card_number: paymentDetails.cardNumber.replace(/\s/g, ''),
      card_holder: paymentDetails.cardName,
      expiry_date: paymentDetails.expiryDate,
      cvv: paymentDetails.cvv
    };
  }

  return await api.put(`/pay-fine/${violationID}`, payload);
};



export const registerVehicle = async (vehicleData) => {
  return await api.post("/register-vehicle", vehicleData);
};

export const addViolation = async (violationData) => {
  return await api.post("/add-violation", violationData);
};

export const login = async (username, password) => {
  return await api.post("/login", { username, password });
};

export const register = async (username, password) => {
  return await api.post("/register", { username, password });
};

// Add more API calls as needed