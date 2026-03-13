# Use the official Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy all your frontend files into the container
COPY . .

# Expose the port the server will run on
EXPOSE 8080

# Run the Python HTTP server
CMD ["python", "-m", "http.server", "8080"]