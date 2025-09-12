packer {
  required_plugins {
    googlecompute = {
      source  = "github.com/hashicorp/googlecompute"
      version = ">= 1.0.0"
    }
  }
}

variable "project_id" {
  type = string
}

variable "image_name" {
  type = string
}

variable "app_version" {
  type    = string
  default = "dev"
}

source "googlecompute" "debian" {
  project_id          = var.project_id
  machine_type        = "e2-medium"
  source_image_family = "debian-11"
  zone                = "asia-south1-b"
  disk_size           = 20
  ssh_username        = "packer"
  image_name          = var.image_name
  image_family        = "hiringdog-app"
}

build {
  sources = ["source.googlecompute.debian"]
  
  # Copy your application code
  provisioner "file" {
    source      = "./"
    destination = "/tmp/app/"
  }
  
  provisioner "shell" {
    inline = [
      # Update system
      "sudo apt-get update -y",
      "sudo apt-get upgrade -y",
      
      # Install Python, pip, venv
      "sudo apt-get install -y python3 python3-pip python3-venv curl",
      
      # Create app directory and copy files
      "sudo mkdir -p /opt/hiringdog",
      "sudo cp -r /tmp/app/* /opt/hiringdog/",
      "sudo chown -R www-data:www-data /opt/hiringdog",
      
      # Install Python dependencies
      "cd /opt/hiringdog && sudo pip3 install -r requirements.txt",
      "sudo pip3 install gunicorn",
      
      # Install and configure Nginx
      "sudo apt-get install -y nginx",
      
      # Create Gunicorn systemd service
      "sudo tee /etc/systemd/system/hiringdog.service > /dev/null <<EOF",
      "[Unit]",
      "Description=Gunicorn instance to serve Hiringdog",
      "After=network.target",
      "",
      "[Service]",
      "User=www-data",
      "Group=www-data",
      "WorkingDirectory=/opt/hiringdog",
      "ExecStart=/usr/local/bin/gunicorn --workers 3 --bind unix:/opt/hiringdog/hiringdog.sock wsgi:app",
      "Restart=always",
      "",
      "[Install]",
      "WantedBy=multi-user.target",
      "EOF",
      
      # Enable Gunicorn service
      "sudo systemctl enable hiringdog",
      
      # Configure Nginx
      "sudo tee /etc/nginx/sites-available/hiringdog > /dev/null <<EOF",
      "server {",
      "    listen 80;",
      "    server_name _;",
      "",
      "    location / {",
      "        proxy_pass http://unix:/opt/hiringdog/hiringdog.sock;",
      "        proxy_set_header Host \\$host;",
      "        proxy_set_header X-Real-IP \\$remote_addr;",
      "        proxy_set_header X-Forwarded-For \\$proxy_add_x_forwarded_for;",
      "        proxy_set_header X-Forwarded-Proto \\$scheme;",
      "    }",
      "",
      "    location /health {",
      "        return 200 'healthy';",
      "        add_header Content-Type text/plain;",
      "    }",
      "}",
      "EOF",
      
      # Enable Nginx site
      "sudo ln -sf /etc/nginx/sites-available/hiringdog /etc/nginx/sites-enabled/",
      "sudo rm -f /etc/nginx/sites-enabled/default",
      
      # Test Nginx config
      "sudo nginx -t",
      
      # Enable Nginx
      "sudo systemctl enable nginx",
      
      # Clean up
      "sudo apt-get autoremove -y",
      "sudo apt-get autoclean"
    ]
  }
}
