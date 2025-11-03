// PDF Export Functionality

// Initialize PDF export when the page loads
document.addEventListener('DOMContentLoaded', function() {
    // Add click event listener to the export button
    const exportBtn = document.querySelector('.export-pdf-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', handleExportClick);
    }
});

async function handleExportClick() {
    const btn = this;
    try {
        console.log('Starting PDF export...');
        
        // Show loading state
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Generating...';
        
        // Export to PDF
        await exportToPDF();
    } catch (error) {
        console.error('Error in PDF export:', error);
        alert('Error generating PDF: ' + error.message);
    } finally {
        // Reset button state
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-download fa-sm text-white-50"></i> Generate Report';
        }
    }
}

async function exportToPDF() {
    // Load required libraries
    await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');
    await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf-autotable/3.5.25/jspdf.plugin.autotable.min.js');
    
    // Initialize jsPDF
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4'
    });
    
    // Add title
    doc.setFontSize(20);
    doc.text('Sales Report - ' + new Date().toLocaleDateString(), 14, 20);
    
    // Add sales chart if available
    const chartCanvas = document.getElementById('salesChart');
    let yPosition = 30; // Starting Y position after title
    
    if (chartCanvas) {
        try {
            await loadScript('https://html2canvas.hertzen.com/dist/html2canvas.min.js');
            const chartImage = await html2canvas(chartCanvas, {
                scale: 2,
                useCORS: true,
                logging: false
            }).then(canvas => canvas.toDataURL('image/png'));
            
            // Add chart image to PDF
            const imgWidth = 180;
            const imgHeight = 80;
            doc.addImage(chartImage, 'PNG', 15, yPosition, imgWidth, imgHeight);
            yPosition += imgHeight + 10;
        } catch (e) {
            console.error('Error adding pie chart to PDF:', e);
            doc.text('Error: Could not include order status chart', 14, yPosition);
            yPosition += 20;
        }
    }
    
    // Add recent orders table
    doc.setFontSize(14);
    doc.text('Recent Orders', 14, yPosition);
    yPosition += 10;
    
    // Prepare table data
    const orders = [];
    const orderTable = document.getElementById('recentOrdersTable');
    
    if (orderTable) {
        const orderRows = orderTable.querySelectorAll('tbody tr');
        
        orderRows.forEach(row => {
            const cells = row.querySelectorAll('td');
            if (cells.length >= 5) {
                orders.push([
                    cells[0].textContent.trim(),
                    cells[1].textContent.trim(),
                    cells[2].textContent.trim(),
                    cells[3].textContent.trim(),
                    cells[4].textContent.trim()
                ]);
            }
        });
        
        // Add table if we have data
        if (orders.length > 0) {
            doc.autoTable({
                head: [['Order ID', 'Customer', 'Date', 'Items', 'Total']],
                body: orders,
                startY: yPosition,
                margin: { top: 10, right: 10, bottom: 10, left: 10 },
                headStyles: {
                    fillColor: [78, 115, 223],
                    textColor: 255,
                    fontStyle: 'bold'
                },
                styles: {
                    cellPadding: 2,
                    fontSize: 8,
                    valign: 'middle',
                    overflow: 'linebreak',
                    cellWidth: 'wrap'
                },
                columnStyles: {
                    0: { cellWidth: 20 },  // Order ID
                    1: { cellWidth: 30 },  // Customer
                    2: { cellWidth: 25 },  // Date
                    3: { cellWidth: 15 },  // Items
                    4: { cellWidth: 20 }   // Total
                },
                didDrawPage: function(data) {
                    // Add page numbers
                    const pageCount = doc.internal.getNumberOfPages();
                    doc.setFontSize(10);
                    doc.setTextColor(150);
                    doc.text(
                        'Page ' + data.pageNumber + ' of ' + pageCount,
                        doc.internal.pageSize.width / 2,
                        doc.internal.pageSize.height - 10,
                        { align: 'center' }
                    );
                }
            });
        } else {
            doc.text('No order data available', 14, yPosition);
        }
    }
    
    // Save the PDF
    doc.save('sales-report-' + new Date().toISOString().split('T')[0] + '.pdf');
}

// Helper function to load scripts dynamically
function loadScript(src) {
    return new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${src}"]`)) {
            resolve();
            return;
        }
        
        const script = document.createElement('script');
        script.src = src;
        script.onload = resolve;
        script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
        document.head.appendChild(script);
    });
}
