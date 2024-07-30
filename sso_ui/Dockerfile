# Use an official Node runtime as a parent image
FROM node:16-alpine

# Set the working directory
WORKDIR /app

# Copy all files to the working directory
COPY . .

# Install a simple static file server
RUN npm install -g http-server

# Expose port 3100
EXPOSE 3100

# Serve the static files
CMD ["http-server", ".", "-p", "3100"]
